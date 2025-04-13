from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
import re
import os
import gc
import torch
import concurrent.futures
import time
from functools import partial

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "https://video-summarizer-iota.vercel.app"}})
print("CORS enabled for https://video-summarizer-iota.vercel.app")

# Global variables for model and tokenizer
summariser = None
model = None
tokenizer = None

# Load the summarization model once at app startup with quantization
print("Loading summarization model at app startup...")
try:
    # Force CPU usage and enable quantization for better performance
    device = -1  # CPU
    
    # Option 1: Load with pipeline (original approach but with quantization)
    # summariser = pipeline("summarization", model="sshleifer/distilbart-cnn-6-6", device=device)
    
    # Option 2: Load model and tokenizer separately for more control and quantization
    model_name = "sshleifer/distilbart-cnn-6-6"  # Smaller, faster model than the 12-6 version
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    # Load with 8-bit quantization if bitsandbytes is available
    try:
        from bitsandbytes.nn import Linear8bitLt
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name, device_map="auto", load_in_8bit=True)
        print("✅ Model loaded with 8-bit quantization")
    except ImportError:
        # Fall back to regular loading if bitsandbytes is not available
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        model.to(f"cpu")
        print("✅ Model loaded without quantization (bitsandbytes not available)")
    
    # Create summarizer function
    def summarize_text(text, max_length=150, min_length=40):
        inputs = tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        else:
            inputs = {k: v.to("cpu") for k, v in inputs.items()}
            
        summary_ids = model.generate(
            inputs["input_ids"], 
            max_length=max_length, 
            min_length=min_length,
            do_sample=False
        )
        summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        return summary
    
    # Assign the function to the global summariser variable
    summariser = summarize_text
    print("✅ Custom summarization function created")
    
except Exception as e:
    print(f"❌ Error loading model: {str(e)}")
    summariser = None
    model = None
    tokenizer = None

@app.route('/api/summarize_youtube', methods=['GET'])
def debug_get():
    print("⚠️  Received unexpected GET request to /api/summarize_youtube")
    print(f"🔍 Method: {request.method}")
    print(f"🌐 Remote IP: {request.remote_addr}")
    print(f"🧾 Headers: {dict(request.headers)}")
    print(f"🔗 Full URL: {request.url}")
    print(f"📱 User-Agent: {request.headers.get('User-Agent')}")
    print(f"🪪 Referer: {request.headers.get('Referer')}")
    print(f"🔐 Origin: {request.headers.get('Origin')}")
    
    return jsonify({"error": "Only POST allowed"}), 405

def get_video_id_from_url(url):
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
    return video_id_match.group(1) if video_id_match else None

@app.route("/")
def home():
    return "Flask YouTube summarizer is running!"

@app.route('/api/summarize_youtube', methods=['POST'], strict_slashes=False)
def summary_api():
    # Check if model was loaded successfully
    if summariser is None or (model is None and tokenizer is None):
        return jsonify({'error': 'Summarization model failed to load'}), 500
        
    data = request.get_json()
    print("📩 Incoming request:", data)
    url = data.get('url', '')

    video_id = get_video_id_from_url(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        start_time = time.time()
        
        # Set a timeout for the transcript fetch
        transcript = get_transcript(video_id)
        
        # Process transcript in parallel
        summary = get_summary_parallel(transcript)
        
        # Calculate and log processing time
        processing_time = time.time() - start_time
        print(f"⏱️ Total processing time: {processing_time:.2f} seconds")
        
        # Clear CUDA cache if using GPU
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
        # Force garbage collection
        gc.collect()
        
        return jsonify({'summary': summary}), 200
    except Exception as e:
        print("🔥 ERROR:", str(e))
        return jsonify({'error': str(e)}), 500

def get_transcript(video_id):
    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
    transcript = ' '.join([d['text'] for d in transcript_list])
    return transcript

def process_chunk(chunk, chunk_index):
    """Process a single chunk and return its summary"""
    try:
        start_time = time.time()
        
        input_length = len(chunk.split())
        max_length = int(min(150, max(40, input_length * 0.5)))
        min_length = min(40, max(20, input_length * 0.3))  # Adjusted min_length
        
        print(f"Chunk {chunk_index}: {len(chunk)} chars, ~{len(chunk.split())} words")
        
        # Use the global summariser function
        summary = summariser(chunk, max_length=max_length, min_length=min_length)
        
        processing_time = time.time() - start_time
        print(f"Chunk {chunk_index} processed in {processing_time:.2f} seconds. Input length: {input_length}, Output length: {len(summary.split())}")
        
        return summary
    except Exception as e:
        print(f"🧨 Summary generation failed for chunk {chunk_index}, length {len(chunk)}")
        print(f"❗ Error: {str(e)}")
        return f"[Error summarizing chunk {chunk_index}]"

def get_summary_parallel(text, max_chunk_size=400, max_workers=6):
    """Process chunks in parallel using ThreadPoolExecutor"""
    # Simple fixed-length chunking
    chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
    print(f"Transcript length: {len(text)}, chunks: {len(chunks)}")
    
    # Use ThreadPoolExecutor for parallel processing
    # Adjust max_workers based on available CPUs (use fewer workers than available CPUs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create a partial function with the chunk_index parameter
        process_chunk_with_index = partial(process_chunk)
        
        # Submit all chunks for processing with their indices
        future_to_chunk = {
            executor.submit(process_chunk_with_index, chunk, i): i 
            for i, chunk in enumerate(chunks)
        }
        
        # Collect results in order
        summaries = [""] * len(chunks)
        for future in concurrent.futures.as_completed(future_to_chunk):
            chunk_index = future_to_chunk[future]
            try:
                summary = future.result()
                summaries[chunk_index] = summary
            except Exception as e:
                print(f"🧨 Error processing chunk {chunk_index}: {str(e)}")
                summaries[chunk_index] = f"[Error summarizing chunk {chunk_index}]"
    
    return " ".join(summaries)

# For Railway
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
