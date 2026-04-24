 # llama_server.py
from flask import Flask, request, jsonify
import subprocess
import threading
import time
import os
import random

app = Flask(__name__)


class LlamaServer:
    def __init__(self, model_path: str, host: str = "localhost", port: int = 8000):
        self.model_path = model_path
        self.host = host
        self.port = port
        self.process = None

    def start_server(self):
        """Запускает Llama сервер"""
        try:
            # Проверяем доступность ollama
            result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                cmd = ["ollama", "serve"]
                self.process = subprocess.Popen(cmd)
                print(f"✅ Llama сервер запущен на {self.host}:{self.port}")
                return True
            else:
                print("⚠️ Ollama не найден, запускаем в режиме улучшенной заглушки")
                return True
        except Exception as e:
            print(f"⚠️ Ошибка запуска Llama, режим улучшенной заглушки: {e}")
            return True  # Всегда возвращаем True для работы в режиме заглушки

    def stop_server(self):
        """Останавливает Llama сервер"""
        if self.process:
            self.process.terminate()


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "llama_server", "mode": "enhanced_fallback"})


@app.route('/v1/completions', methods=['POST'])
def generate_completion():
    try:
        data = request.json
        prompt = data.get('prompt', '')

        prompt_lower = prompt.lower()

        if any(word in prompt_lower for word in ["мафия", "mafia", "дон"]):
            responses = [
                "Как член мафиозной семьи, я действую в интересах нашей организации.",
                "Тишина и скрытность - наши главные союзники в этой игре.",
                "Каждое действие должно быть тщательно продумано для победы.",
                "Мы должны устранять самых опасных и наблюдательных игроков."
            ]
        elif any(word in prompt_lower for word in ["шериф", "sheriff"]):
            responses = [
                "Правда всегда выходит наружу. Мое дело - способствовать этому.",
                "Каждую ночь я приближаюсь к разгадке этой тайны.",
                "Наблюдение и анализ - мои главные инструменты.",
                "Я должен быть осторожен, но решительным в своих действиях."
            ]
        elif any(word in prompt_lower for word in ["доктор", "doctor"]):
            responses = [
                "Каждая спасенная жизнь - это шаг к победе справедливости.",
                "Я должен выбирать тех, кто наиболее ценен для города.",
                "Моя задача - сохранять баланс между жизнью и смертью.",
                "Интуиция и опыт помогают мне делать правильный выбор."
            ]
        elif any(word in prompt_lower for word in ["маньяк", "maniac"]):
            responses = [
                "Хаос - мой лучший друг в этой игре!",
                "Чем больше страха, тем интереснее становится...",
                "Я наслаждаюсь каждой минутой этого безумия!",
                "Кровь и ужас - вот настоящая красота этой ночи."
            ]
        elif any(word in prompt_lower for word in ["путана", "whore"]):
            responses = [
                "Ночью я узнаю самые сокровенные секреты этого города...",
                "Защита невинных - это искусство, которым я владею.",
                "Я вижу то, что скрыто от глаз обычных людей.",
                "Доверие и интуиция - мои главные инструменты."
            ]
        elif any(word in prompt_lower for word in ["журналист", "journalist"]):
            responses = [
                "Информация - это сила, и я знаю, как ею распорядиться.",
                "Мое расследование приближает нас к истине.",
                "Каждая деталь может стать ключом к разгадке.",
                "Правда всегда стоит того, чтобы ее искать."
            ]
        else:
            responses = [
                "Я внимательно анализирую ситуацию и поведение всех игроков.",
                "Каждое решение должно быть взвешенным и обоснованным.",
                "Правда откроется тем, кто умеет слушать и наблюдать.",
                "В этой игре важно сохранять хладнокровие и логику.",
                "Я доверяю своим инстинктам и наблюдениям."
            ]

        response_text = random.choice(responses)

        response_text = (response_text
                         .replace("{target}", "этот игрок")
                         .replace("  ", " ")
                         .strip())

        if not response_text[-1] in ".!?":
            response_text += random.choice(["", "!", "..."])

        return jsonify({
            "choices": [{"text": response_text, "index": 0, "finish_reason": "length"}]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    server = LlamaServer("")
    if server.start_server():
        # Даем серверу время на запуск
        time.sleep(2)
        print("🚀 Запуск Flask сервера Llama с улучшенной заглушкой...")
        app.run(host='localhost', port=8080, debug=False, use_reloader=False)