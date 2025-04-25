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
import threading
import nltk
from nltk.tokenize import sent_tokenize

# Download NLTK data for sentence tokenization
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["https://video-summarizer-iota.vercel.app","http://localhost:3000"]}})
print("CORS enabled for https://video-summarizer-iota.vercel.app")

# Global variables for model and tokenizer
summariser = None
model = None
tokenizer = None
model_last_used = None
model_lock = threading.Lock()

# Configuration
MODEL_NAME = "philschmid/bart-large-cnn-samsum"  # Better model for dialogue summarization
MODEL_UNLOAD_DELAY = 300  # seconds (5 minutes)
CHUNK_OVERLAP = 50  # Number of words to overlap between chunks for better context

# Unloader thread function
def model_unloader():
    global model, tokenizer, summariser, model_last_used
    while True:
        time.sleep(60)  # Check every minute
        with model_lock:
            if model and model_last_used and (time.time() - model_last_used > MODEL_UNLOAD_DELAY):
                print("Unloading model due to inactivity...")
                del model
                del tokenizer
                del summariser
                model = tokenizer = summariser = None
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                print("✅ Model unloaded successfully")
                model_last_used = None

# Start unloader thread
threading.Thread(target=model_unloader, daemon=True).start()
print("✅ Model unloader thread started")

# Function to load model on demand
def load_model():
    global model, tokenizer, summariser, model_last_used
    with model_lock:
        if not model:
            print(f"Loading summarization model: {MODEL_NAME}...")
            try:
                # Force CPU usage
                device = -1  # CPU
                
                # Load model and tokenizer separately for more control
                tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
                model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
                model.to("cpu")
                print("✅ Model loaded successfully")
                
                # Create summarizer function
                def summarize_text(text, max_length=150, min_length=40):
                    inputs = tokenizer(text, return_tensors="pt", max_length=1024, truncation=True)
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
                raise
        
        # Update last used timestamp
        model_last_used = time.time()

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
    try:
        # Load model on demand
        load_model()
        
        # Check if model was loaded successfully
        if summariser is None or model is None or tokenizer is None:
            return jsonify({'error': 'Summarization model failed to load'}), 500
            
        data = request.get_json()
        print("📩 Incoming request:", data)
        url = data.get('url', '')

        video_id = get_video_id_from_url(url)
        if not video_id:
            return jsonify({'error': 'Invalid YouTube URL'}), 400

        start_time = time.time()
        
        # Set a timeout for the transcript fetch
        transcript = get_transcript(video_id)
        
        # Process transcript in parallel with semantic chunking
        summary = get_summary_parallel(transcript)
        
        # Calculate and log processing time
        processing_time = time.time() - start_time
        print(f"⏱️ Total processing time: {processing_time:.2f} seconds")
        
        # Force garbage collection
        gc.collect()
        
        # Update model last used time
        with model_lock:
            global model_last_used
            model_last_used = time.time()
        
        return jsonify({'summary': summary}), 200
    except Exception as e:
        print("🔥 ERROR:", str(e))
        return jsonify({'error': str(e)}), 500

def get_transcript(video_id):
    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
    transcript = ' '.join([d['text'] for d in transcript_list])
    return transcript

def create_semantic_chunks(text, max_chunk_size=500):
    """Create chunks based on sentences to maintain semantic coherence"""
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence_words = len(sentence.split())
        
        # If adding this sentence would exceed max size and we already have content,
        # finish the current chunk and start a new one
        if current_length + sentence_words > max_chunk_size and current_length > 0:
            chunk_text = ' '.join(current_chunk)
            chunks.append(chunk_text)
            
            # Start new chunk with overlap - take the last sentence or two from previous chunk
            overlap_start = max(0, len(current_chunk) - 3)  # Take up to 3 sentences for overlap
            current_chunk = current_chunk[overlap_start:]
            current_length = sum(len(s.split()) for s in current_chunk)
        
        current_chunk.append(sentence)
        current_length += sentence_words
    
    # Add the last chunk if it has content
    if current_length > 0:
        chunk_text = ' '.join(current_chunk)
        chunks.append(chunk_text)
    
    return chunks

def process_chunk(chunk, chunk_index):
    """Process a single chunk and return its summary"""
    try:
        start_time = time.time()
        
        input_length = len(chunk.split())
        # Adjust max_length based on input size but ensure it's reasonable
        max_length = int(min(150, max(40, input_length * 0.4)))
        min_length = int(min(40, max(20, input_length * 0.2)))
        
        print(f"Chunk {chunk_index}: {len(chunk)} chars, ~{input_length} words")
        
        # Use the global summariser function
        summary = summariser(chunk, max_length=max_length, min_length=min_length)
        
        processing_time = time.time() - start_time
        print(f"Chunk {chunk_index} processed in {processing_time:.2f} seconds. Input length: {input_length}, Output length: {len(summary.split())}")
        
        return summary
    except Exception as e:
        print(f"🧨 Summary generation failed for chunk {chunk_index}, length {len(chunk)}")
        print(f"❗ Error: {str(e)}")
        return f"[Error summarizing chunk {chunk_index}]"

def get_summary_parallel(text, max_workers=4):
    """Process chunks in parallel using ThreadPoolExecutor with semantic chunking"""
    # Create semantic chunks instead of fixed-size chunks
    chunks = create_semantic_chunks(text)
    print(f"Transcript length: {len(text)}, semantic chunks: {len(chunks)}")
    
    # Use ThreadPoolExecutor for parallel processing
    # Reduced max_workers to avoid overwhelming the CPU with the larger model
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
    
    # If we have multiple summaries, perform a second-stage summarization to improve coherence
    if len(summaries) > 1:
        combined_summary = " ".join(summaries)
        
        # If the combined summary is too long, we need to summarize it again
        if len(combined_summary.split()) > 1000:
            print("Performing second-stage summarization for coherence...")
            try:
                # Use a higher min_length for the final summary to ensure it's comprehensive
                final_summary = summariser(combined_summary, max_length=250, min_length=100)
                return final_summary
            except Exception as e:
                print(f"🧨 Second-stage summarization failed: {str(e)}")
                # Fall back to the combined summary if second-stage fails
                return combined_summary
        else:
            return combined_summary
    else:
        # If there's only one chunk, just return its summary
        return summaries[0]

# For Railway
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
