import express from 'express';
import path from 'path';
import { fileURLToPath } from 'url';
import axios from 'axios'; // <-- ADD THIS

const app = express();
const PORT = process.env.PORT || 4000;

// Get __dirname in ES module context
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Middleware to parse JSON
app.use(express.json());

// Serve static files from the React app
app.use(express.static(path.join(__dirname, '../build')));

// Proxy to Flask backend for /summary
app.get('/summary', async (req, res) => {
  const { url } = req.query;
  try {
    const flaskResponse = await axios.get('http://localhost:5000/summary', {
      params: { url },
    });
    res.json(flaskResponse.data);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Example API route (optional)
app.get('/api/hello', (req, res) => {
  res.json({ message: 'Hello from Express backend!' });
});

// Catch-all route to serve frontend
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../build', 'index.html'));
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
