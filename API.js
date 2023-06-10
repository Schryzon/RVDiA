/*
G-Tech Re'sman News API
Created by none other than Schryzon (Jayananda)
Natha sih gak mau buatin ga niat kali mu broooo
*/

// Import modules (Node JS v16)
const http = require('http')
const fs = require('fs')
require('dotenv').config()
const { MongoClient, Promise } = require('mongodb')
const uri = process.env.mongodburl
const mongo = new MongoClient(uri, { useNewUrlParser: true, useUnifiedTopology: true });
const port = process.env.PORT || 8001

// Async connection to MongoDB
const connectDatabase = async(collection) => {
    await mongo.connect()
    const data = mongo.db('Main').collection(collection)
    return data
}

// Server code
const server = async() => {
    const collData = await connectDatabase('Technews')
    const newsData = await collData.findOne({
        '_id': 1
    })
    const displayText = JSON.stringify(newsData)
    const httpServer = http.createServer(function(req, res){
    res.writeHead(200, {'Content-Type': 'application/json'})
    if (displayText) {
        res.write(displayText);
      } else {
        res.write('Belum ada data berita, sayangku!');
      }
    res.end()
    })

    httpServer.listen(port, function(error){
        if(error){
            console.log(`Error: ${error}`)
        }else{
            console.log(`Listening: ${port}`)
        }
    })
}

server()