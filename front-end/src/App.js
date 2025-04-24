import React, { useState } from 'react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_API_URL;

function App() {
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [summary, setSummary] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [videoId, setVideoId] = useState(null);

  const getYouTubeVideoId = (url) => {
    const regex = /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/;
    const match = url.match(regex);
    return match ? match[1] : null;
  };

  const handleYoutubeSubmit = async (e) => {
    e.preventDefault();
    if (!youtubeUrl) return;

    try {
      setLoading(true);
      setError('');
      setSummary('');
      setVideoId(null);

      const response = await axios.post(`${API_URL}/api/summarize_youtube`, {
        url: youtubeUrl,
      });

      setSummary(response.data.summary);

      const extractedId = getYouTubeVideoId(youtubeUrl);
      if (extractedId) setVideoId(extractedId);
      else throw new Error('Invalid YouTube URL format.');
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Failed to process YouTube video');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen w-full bg-gradient-to-r from-[#536976] to-[#BBD2C5] flex items-center justify-center p-6">
      <div className="flex flex-col lg:flex-row gap-6 w-full max-w-6xl h-[50vh] items-center justify-center">
        <div className="flex flex-col items-center justify-center p-6 w-full lg:w-[43vw] h-full bg-white border border-black rounded-2xl shadow-2xl">
          <h1 className="text-4xl font-bold mb-6 font-montserrat text-gray-800">YouTube Summarizer</h1>
          <form onSubmit={handleYoutubeSubmit} className="flex flex-col items-center gap-4 w-full">
            <input
              type="text"
              placeholder="Paste YouTube video URL..."
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              className="w-full h-12 px-4 rounded-md border border-gray-400 text-lg placeholder:italic placeholder:text-gray-400"
            />
            <button
              type="submit"
              disabled={loading || !youtubeUrl}
              className={`w-52 h-10 rounded-md border text-white font-semibold ${
                loading || !youtubeUrl
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 transition'
              }`}
            >
              {loading ? 'Summarizing...' : 'Summarize'}
            </button>
          </form>
          {error && (
            <div className="mt-4 text-red-700 bg-red-100 border border-red-400 p-2 rounded-md text-sm text-center">
              {error}
            </div>
          )}
        </div>

        {summary && videoId && (
          <div className="flex flex-col items-center justify-start w-full lg:w-[43vw] h-full p-4 bg-white border border-black rounded-2xl shadow-2xl">
            <iframe
              className="rounded-md mb-4"
              width="100%"
              height="230"
              src={`https://www.youtube.com/embed/${videoId}`}
              title="YouTube video player"
              frameBorder="0"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
            ></iframe>
            <h2 className="text-3xl font-semibold mb-2 text-gray-800">Summary</h2>
            <div className="text-gray-700 text-base leading-relaxed whitespace-pre-wrap overflow-auto max-h-40">
              {summary}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
