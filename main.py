from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from pathlib import Path
from contextlib import asynccontextmanager
import json
import os
from dotenv import load_dotenv
from rlm_session import REPLSession, SimpleRLM

# Load environment variables from .env file
load_dotenv()

# Configuration
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

if not ANTHROPIC_API_KEY:
    print("Warning: ANTHROPIC_API_KEY not set. RLM queries will fail.")

# Simple in-memory storage (in production, use Redis or DB)
active_sessions = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    yield
    # Shutdown - clean up all sessions
    for doc_id in list(active_sessions.keys()):
        active_sessions[doc_id]['session'].cleanup()


app = FastAPI(title="RLM Proof of Concept", lifespan=lifespan)


@app.get("/")
def read_root():
    return {
        "message": "RLM Proof of Concept",
        "endpoints": {
            "upload": "POST /upload - Upload a JSON document",
            "query": "POST /query - Query a document using RLM",
            "cleanup": "POST /cleanup/{doc_id} - Clean up a session"
        }
    }


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a JSON document for RLM processing"""
    
    # Validate JSON
    try:
        content = await file.read()
        json.loads(content)  # Validate it's valid JSON
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    
    # Save file
    doc_id = file.filename.replace('.json', '')
    file_path = UPLOAD_DIR / f"{doc_id}.json"
    
    with open(file_path, 'wb') as f:
        f.write(content)
    
    return {
        "doc_id": doc_id,
        "message": f"Document uploaded successfully",
        "file_path": str(file_path)
    }


@app.post("/query")
async def query_document(
    doc_id: str = Form(...),
    query: str = Form(...),
    max_iterations: int = Form(default=5)
):
    """Query a document using RLM approach"""
    
    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY not configured"
        )
    
    file_path = UPLOAD_DIR / f"{doc_id}.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Create or reuse REPL session
    if doc_id not in active_sessions:
        session = REPLSession(str(file_path))
        session.start()
        active_sessions[doc_id] = {
            'session': session,
            'history': []
        }
    
    session_data = active_sessions[doc_id]
    session = session_data['session']
    rlm = SimpleRLM(ANTHROPIC_API_KEY)
    
    # Exploration loop
    conversation_history = []
    
    try:
        for i in range(max_iterations):
            print(f"\n=== Iteration {i+1} ===")
            
            # Generate exploration code
            code = rlm.generate_exploration_code(query, conversation_history)
            print(f"Generated code:\n{code}")
            
            # Execute in REPL
            result = session.execute(code)
            print(f"Output: {result['stdout']}")
            
            if not result['success']:
                print(f"Error: {result['stderr']}")
            
            # Record this iteration
            conversation_history.append({
                'iteration': i + 1,
                'code': code,
                'output': result['stdout'] if result['success'] else f"ERROR: {result['stderr']}"
            })

            # Improved stopping: run minimum 2 iterations, stop if we see actual data values
            if i >= 1 and result['success']:
                output = result['stdout']
                output_lower = output.lower()

                # Stop if we see currency symbols (strong indicator of actual values)
                if '$' in output or '€' in output or '£' in output:
                    break

                # Or if we see key-value pairs with revenue/profit data
                has_data_keyword = any(kw in output_lower for kw in ['revenue:', 'profit:', 'expenses:', 'total:'])
                has_number_with_unit = any(unit in output for unit in ['M', 'K', 'million', 'thousand'])

                if has_data_keyword and has_number_with_unit:
                    break
        
        # Formulate final answer
        answer = rlm.formulate_answer(query, conversation_history)
        
        return {
            "query": query,
            "answer": answer,
            "exploration_steps": conversation_history,
            "iterations_used": len(conversation_history)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cleanup/{doc_id}")
def cleanup_session(doc_id: str):
    """Clean up a REPL session"""
    
    if doc_id in active_sessions:
        active_sessions[doc_id]['session'].cleanup()
        del active_sessions[doc_id]
        return {"message": f"Session for {doc_id} cleaned up"}
    
    return {"message": "No active session found"}