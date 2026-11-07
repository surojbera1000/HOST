// pm2 process file: `pm2 start ecosystem.config.cjs`
module.exports = {
  apps: [
    {
      name: "miku-otp-bot",
      script: "dist/main.js",
      instances: 1,
      autorestart: true,
      max_restarts: 20,
      env: { NODE_ENV: "production" },
    },
  ],
};
