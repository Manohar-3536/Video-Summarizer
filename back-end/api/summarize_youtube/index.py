from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from transformers import pipeline
import re
import os

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "https://video-summarizer-iota.vercel.app"}})
print("CORS enabled for https://video-summarizer-iota.vercel.app")

# Initialize summarizer
# summariser = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")
summariser = pipeline("summarization", model="knkarthick/MEETING_SUMMARY")


def get_video_id_from_url(url):
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
    return video_id_match.group(1) if video_id_match else None

@app.route("/")
def home():
    return "Flask YouTube summarizer is running!"

@app.route('/api/summarize_youtube', methods=['POST']) 
@app.route('/api/summarize_youtube/', methods=['POST'])
def summary_api():
    data = request.get_json()
    print("📩 Incoming request:", data)
    url = data.get('url', '')

    video_id = get_video_id_from_url(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        transcript = get_transcript(video_id)
        summary = get_summary(transcript)
        return jsonify({'summary': summary}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_transcript(video_id):
    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
    transcript = ' '.join([d['text'] for d in transcript_list])
    return transcript

def get_summary(text, max_chunk_size=1000):
    # Break text into sentence-based chunks
    sentences = re.split(r'(?<=[.?!])\s+', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    if current_chunk:
        chunks.append(current_chunk.strip())

    summaries = []
    for chunk in chunks:
        summary = summariser(chunk, max_length=150, min_length=40, do_sample=False)[0]['summary_text']
        summaries.append(summary)

    return " ".join(summaries)

# For platforms like Railway
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
