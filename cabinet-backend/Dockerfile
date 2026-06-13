FROM node:20-slim
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY . .
RUN mkdir -p /app/data
ENV PORT=8090 DB_FILE=/app/data/db.json
EXPOSE 8090
CMD ["node", "server.js"]
