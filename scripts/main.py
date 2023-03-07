import pymongo
import discord
from cogs.Handler import NotInGTechServer, NotGTechMember, NotGTechAdmin
from discord.ext import commands
import os
from dotenv import load_dotenv
load_dotenv('./.gitignore/secrets.env')

client = pymongo.MongoClient(os.getenv('mongodburl'))

def connectdb(collection:str):
    db = client.Main
    coll = db[collection]
    return coll

def in_gtech_server():
    async def predicate(ctx):
        if not ctx.guild.id == 997500206511833128:
            raise NotInGTechServer('Not in the G-Tech server!')
        return True
    return commands.check(predicate)

def is_member_check():
    db = connectdb("Gtech")
    async def predicate(ctx):
        data = db.find_one({'_id':ctx.author.id})
        if data is None:
            raise NotGTechMember('Not a G-Tech member!')
        return True
    return commands.check(predicate)

def is_perangkat():
    async def predicate(ctx):
        perangkat = [
            893152351689527326, 919461305432305685, 877008612021661726, 632930926522925056,
            745218212689477642, 892293912964767784, 866890432038567949
            # Ayuning, Nisa, Jayananda, Ditha, Cok Is, Nanda Maharani, Richonanta
        ]
        if not ctx.author.id in perangkat:
            raise NotGTechAdmin('Not a G-Tech admin!')
        return True
    return commands.check(predicate)

def wind_heading(direction:int):
        result =[]
        ranges = [
                [0, 46], [46, 91],
                [90, 136], [136, 181],
                [180, 226], [225, 271],
                [270, 316], [315, 361]
                ]
        
        for i in ranges:
            if direction in range(i[0], i[1]):
              result.append(i)
        
        if len(result) == 2:
            if result == [ranges[1], ranges[2]]:
                return "Timur"
            elif result == [ranges[3], ranges[4]]:
                return "Selatan"
            elif result == [ranges[5], ranges[6]]:
                return "Barat"
            else:
                return "Utara"
            
        else:
            if result == [ranges[0]] or result == [ranges[1]]:
                return "Timur Laut"
            elif result == [ranges[2]] or result == [ranges[3]]:
                return "Tenggara"
            elif result == [ranges[4]] or result == [ranges[5]]:
                return "Barat Daya"
            else:
                return "Barat Laut"
            