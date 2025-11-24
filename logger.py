import logging.handlers
import os
import queue

# Абсолютный путь для лога
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(script_dir, 'app.log')

# Создаём очередь без ограничения размера
que = queue.Queue(-1)

# Обработчик для очереди (прикрепляется к логгеру)
queue_handler = logging.handlers.QueueHandler(que)

# Обработчик для консоли
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Обработчик для файла (append mode)
file_handler = logging.FileHandler(log_file, mode='a')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Listener, который обрабатывает очередь в отдельном потоке
listener = logging.handlers.QueueListener(que, stream_handler, file_handler)

# Настраиваем root-логгер
root = logging.getLogger()
root.setLevel(logging.DEBUG)  # Уровень DEBUG для всех логов
root.addHandler(queue_handler)

# Запускаем listener
listener.start()
