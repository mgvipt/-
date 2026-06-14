FROM node:20-slim

# ffmpeg + збірка whisper.cpp (безкоштовна локальна транскрибація)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg git build-essential cmake ca-certificates curl wget && \
    rm -rf /var/lib/apt/lists/*

# whisper.cpp + модель (small ~466MB; для кращої якості укр/рос — medium, див. ARG)
ARG WHISPER_MODEL_NAME=small
RUN git clone --depth=1 https://github.com/ggerganov/whisper.cpp /opt/whisper && \
    cd /opt/whisper && cmake -B build && cmake --build build --config Release -j && \
    bash ./models/download-ggml-model.sh ${WHISPER_MODEL_NAME}
ENV WHISPER_BIN=/opt/whisper/build/bin/whisper-cli \
    WHISPER_MODEL=/opt/whisper/models/ggml-${WHISPER_MODEL_NAME}.bin

WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY . .
ENV PORT=8080
EXPOSE 8080
CMD ["node", "server.js"]
