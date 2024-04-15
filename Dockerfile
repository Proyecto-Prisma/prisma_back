# Utilizar una imagen base de Python
FROM python:3.12.2-slim

# Establece el directorio de trabajo en el contenedor
WORKDIR /app

# Copiar los archivos desde tu proyecto al contenedor
COPY . /app

# Instalar las dependencias del proyecto
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install nltk
RUN pip install wordcloud
RUN pip install xlrd

# Exponer el puerto que utiliza la aplicación
EXPOSE 8080

# Comando para ejecutar la aplicación
CMD ["python", "run.py"]
