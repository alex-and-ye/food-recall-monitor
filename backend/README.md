# Backend

## Steps to run the backend server:

1. Start ChromaDB from the root directory of the project:
   ```bash
   chroma run --path ./backend/.chroma_data --port 8000
   ```

2. Run the backend server:
   ```bash
   fastapi dev main.py --port 8080
   ```