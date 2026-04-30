module.exports = {
  apps: [
    {
      name: "rvdia-bot",
      script: "python",
      args: "RVDIA.py",
      interpreter: "none", // Since we use python directly in script/args
      env: {
        NODE_ENV: "production",
        // You can put your secrets here if not using .env
        // PRISMA_PY_DEBUG: "0",
      },
      // Optional: Delay between restarts
      restart_delay: 3000,
      // Optional: Watch for file changes to restart (might be noisy for bot)
      watch: false,
      // Logging
      error_file: "./logs/err.log",
      out_file: "./logs/out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};
