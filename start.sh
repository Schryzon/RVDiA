#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting deployment sequence..."

# Generate Prisma Client
echo "📦 Generating Prisma Client..."
prisma generate

# Sync Database Schema
# Note: Use --accept-data-loss only if you are sure about fresh starts.
# For first-time deployment on Railway, this is usually needed to create tables.
echo "🔄 Syncing database schema..."
prisma db push --accept-data-loss

# Start the bot
echo "🤖 Launching RVDiA Bot..."
python RVDIA.py
