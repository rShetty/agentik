#!/usr/bin/env python3
"""Start the AgentOS POC HTTP server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
