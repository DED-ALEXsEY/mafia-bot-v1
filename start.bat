@echo off
start /min ollama serve
timeout /t 3
python run_system_paths.py