import React, { useState } from 'react';
import axios from 'axios';

const API_URL = process.env.NODE_ENV === 'production' 
  ? '/api' 
  : 'http://localhost:5000/api';

  function App() {
    const [youtubeUrl, setYoutubeUrl] = useState('');
    const [summary, setSummary] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
  
    const handleYoutubeSubmit = async (e) => {
      e.preventDefault();
      if (!youtubeUrl) return;
  
      try {
        setLoading(true);
        setError('');
        setSummary('');
  
        const response = await axios.post(`${API_URL}/summarize-youtube`, {
          url: youtubeUrl
        });
  
        setSummary(response.data.summary);
      } catch (err) {
        setError(err.response?.data?.error || 'Failed to process YouTube video');
      } finally {
        setLoading(false);
      }
    };
  
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-100 to-purple-100 px-4 py-10">
        <div className="max-w-3xl mx-auto bg-white rounded-2xl shadow-xl p-8">
          <h1 className="text-4xl font-bold text-center text-purple-700 mb-6">
            🎬 YouTube Clip Summarizer
          </h1>
  
          <form onSubmit={handleYoutubeSubmit} className="space-y-4">
            <input
              type="text"
              placeholder="Paste YouTube video URL..."
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-400 focus:outline-none text-lg"
            />
  
            <button
              type="submit"
              disabled={loading || !youtubeUrl}
              className={`w-full py-3 rounded-xl font-semibold text-white transition duration-200 ${
                loading || !youtubeUrl
                  ? 'bg-purple-400 cursor-not-allowed'
                  : 'bg-purple-600 hover:bg-purple-700'
              }`}
            >
              {loading ? 'Summarizing...' : 'Summarize'}
            </button>
          </form>
  
          {error && (
            <div className="mt-6 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg">
              {error}
            </div>
          )}
  
          {summary && (
            <div className="mt-8 bg-purple-50 border border-purple-300 p-6 rounded-xl shadow-sm">
              <h2 className="text-2xl font-semibold text-purple-800 mb-3">📝 Summary</h2>
              <p className="whitespace-pre-wrap text-gray-800 leading-relaxed">{summary}</p>
            </div>
          )}
        </div>
      </div>
    );
  }
  
export default App;

