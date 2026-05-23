#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting deployment sequence..."

if [ "$BOT_TYPE" = "xelvie" ]; then
    echo "🤖 Launching Xelvie Uptime Monitor..."
    python Xelvie.py
else
    # Generate Prisma Client
    echo "📦 Generating Prisma Client..."
    prisma generate

    # Sync Database Schema
    echo "🔄 Syncing database schema..."
    prisma db push --accept-data-loss

    # Start the bot
    echo "🤖 Launching RVDiA Bot..."
    python RVDIA.py
fi
