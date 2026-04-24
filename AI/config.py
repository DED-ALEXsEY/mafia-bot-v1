# config.py
LLAMA_CONFIG = {
    "base_url": "http://localhost:11434",
    "timeout": 30,
    "max_tokens": 250,
    "temperature": 0.95,
    "enabled": True
}

AI_PERSONALITIES = {
    "aggressive": {"temperature": 0.9, "description": "Агрессивный стиль игры"},
    "cautious": {"temperature": 0.3, "description": "Осторожный стиль игры"},
    "neutral": {"temperature": 0.7, "description": "Нейтральный стиль игры"},
    "deceptive": {"temperature": 0.8, "description": "Обманчивый стиль игры"}
}