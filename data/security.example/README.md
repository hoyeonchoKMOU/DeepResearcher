# Security Configuration

This folder contains example configuration files for authentication and API keys.

## Setup Instructions

1. Copy all files from `data/security.example/` to `data/security/`:
   ```bash
   cp data/security.example/*.json data/security/
   ```

2. Edit the files in `data/security/` with your actual credentials:
   - `google_oauth.json`: Google OAuth credentials for Gemini API
   - `api_keys.json`: API keys for external services

## File Descriptions

### google_oauth.json
Google OAuth credentials for Gemini Code Assist:
- `client_id`: Your Google OAuth 2.0 client ID
- `client_secret`: Your Google OAuth 2.0 client secret
- `project_id`: Your GCP project ID (optional)

### api_keys.json
API keys for external academic search services:
- `semantic_scholar_api_key`: Semantic Scholar API key for higher rate limits

## Important Notes

- **NEVER commit files from `data/security/` to git**
- The `data/security/` folder is already in `.gitignore`
- Only commit example files from `data/security.example/`
- Keep your credentials secure and private

## Getting Credentials

### Google OAuth (Gemini API)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the required APIs
4. Create OAuth 2.0 credentials
5. Copy client ID and secret to `google_oauth.json`

### Semantic Scholar API
1. Visit [Semantic Scholar API](https://www.semanticscholar.org/product/api)
2. Request an API key
3. Copy the key to `api_keys.json`
