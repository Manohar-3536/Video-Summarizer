from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from transformers import pipeline
import re
import os

def get_video_id_from_url(url):
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
    return video_id_match.group(1) if video_id_match else None

app = Flask(__name__)
CORS(app)  # Enable CORS
summariser = pipeline('summarization')  # Load the model once

@app.route("/")
def home():
    return "Flask YouTube summarizer is running!"

@app.route('/api/summarize-youtube', methods=['POST'])
def summary_api():
    data = request.get_json()
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

def get_summary(transcript):
    summary = ''
    for i in range(0, len(transcript), 1000):
        chunk = transcript[i:i+1000]
        summary_text = summariser(chunk)[0]['summary_text']
        summary += summary_text + ' '
    return summary.strip()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
