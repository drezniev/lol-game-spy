import discord
from discord.ext import commands
from discord.ext import tasks
import os
import requests
import json
import textwrap

DISCORD_BOT_TOKEN= os.getenv('DISCORD_BOT_TOKEN')  # Get your bot token from environment variables
API_KEY = os.getenv('RIOT_API_KEY')  # Get your API key from environment variables
TIME_BETWEEN_CHECKS = 15 # Time between checking for new games (in seconds)
TIME_BETWEEN_BACKUPS = 86400 # Time between backups (in seconds)
TIME_BETWEEN_SAVE = 300 # Time between saving the database (in seconds)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
guilds = {} # ID of the guild where the bot is used (guild = server)
players_list = [] # List of players to track

#Data structure
'''
    guilds: {
        guild_id: {
            channel_id: channel_id,
            players_list: [
                {
                    "name": "TestName",
                    "region": "eun1",
                    "puuid": "123",
                    "last_game": "{gameID}",
                }
            ]
        }
    }
'''




#On bot start
@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")
    save_database.start() # Start saving the database
    get_last_game.start() # Start checking for new games
    backup_database.start() # Start backing up the database
    

# On bot join a server
@bot.event
async def on_guild_join(guild):
    guilds[guild.id] = {
        "channel_id": None,
        "players_list": []
    }
    print(f"Joined a new guild: {guild.name}")



# Set channel command
@bot.command(name="lgs-set_channel")
async def set_channel(ctx, channel_id : int):
    #Check if the channel exists
    print(bot.get_channel(channel_id))
    channel = bot.get_channel(channel_id)
    if channel is None:
        await ctx.send(f"Channel {channel_id} does not exist.")
        return
    guilds[ctx.guild.id]["channel_id"] = channel_id
    await ctx.send(f"Channel has been set to #{channel}")

# Help command
@bot.command(name="lgs-help")
async def help(ctx):
    # Send a message with all commands
    await ctx.send("List of commands:\n!lgs-set_channel {channel_id} - Set the channel where the bot will send messages\n!lgs-add_player {name} {region} - Add a player to the list\n!lgs-remove_player {name} {region} - Remove a player from the list\n!lgs-list_players - List all players in the list\n!lgs-help - Show this message")

# Add player command
@bot.command(name="lgs-add_player")
async def add_player(ctx, name, region):
    # Get the guild ID as a string
    guild_id = ctx.guild.id
    # Get the guild players list
    guild_players_list = guilds[guild_id]["players_list"]
    # Convert player region to lower case
    region = region.lower()
    match region:
        case "eune":
            region = "eun1"
        case "euw":
            region = "euw1"
        case "na":
            region = "na1"
        case _:
            await ctx.send("Invalid region. Please use EUNE, EUW or NA.")
            return

    # Check if the player exists (if the player exists, get the player's PUUID)
    puuid = check_if_player_exists(name, region)
    if puuid:
        if not guild_players_list:
            guild_players_list.append(
                {
                    "name": name,
                    "region": region,
                    "puuid": puuid,
                    "last_game": ""
                }    
            )
            print(f"Player {name} on region {region} has been saved to the list on server {guild_id}.")
            await ctx.send(f"Player '{name}' has been saved!")
            return
        else:
            for player in guild_players_list:
                if player['name'].lower() == name.lower() and player['region'] == region:
                    print(f"Player {name} on region {region} is already in the list on server {guild_id}.")
                    await ctx.send(f"Player '{name}' on region '{region}' is already in the list.")
                    return
            else:
                guild_players_list.append(
                    {
                        "name": name,
                        "region": region,
                        "puuid": puuid,
                        "last_game": ""
                    }    
                )
                print(f"Player {name} on region {region} has been saved to the list on server {guild_id}.")
                await ctx.send(f"Name '{name}' has been saved!")
                return
    else:
        await ctx.send(f"Player '{name}' on region '{region}' does not exist.")
        return

# Remove player command
@bot.command(name="lgs-remove_player")
async def remove_player(ctx, name, region):
    # Get the guild ID as a string
    guild_id = str(ctx.guild.id)
    # Get the guild players list
    guild_players_list = guilds[guild_id]["players_list"]
    # Convert player region to lower case
    region = region.lower()
    match region:
        case "eune":
            region = "eun1"
        case "euw":
            region = "euw1"
        case "na":
            region = "na1"
        case _:
            await ctx.send("Invalid region. Please use EUNE, EUW or NA.")
            return

    # Check if the player exists (if the player exists, get the player's PUUID)
    for player in guild_players_list:
        if player['name'].lower() == name.lower() and player['region'] == region:
            guild_players_list.remove(player)
            await ctx.send(f"Player '{name}' has been removed!")
            return
    await ctx.send(f"Player '{name}' on region '{region}' does not exist.")
    return

# Show names command
@bot.command(name="lgs-list_players")
async def show_names(ctx):
    # Get the guild ID as a string
    guild_id = str(ctx.guild.id)
    # Get the guild players list
    guild_players_list = guilds[guild_id]["players_list"]
    # List of names to display
    names_str = ""
    if not guild_players_list:
        await ctx.send("The name list is empty.")
    else:
        for player in guild_players_list:
            names_str += player['name'] + " " + player['region'] + "\n"
        await ctx.send(f"List of tracked players:\n```{names_str}```")

# Task to check for new games
@tasks.loop(seconds=TIME_BETWEEN_CHECKS) # Check every 60 seconds
async def get_last_game():
    print("Checking for new games...")
    for guild in guilds:
        # Check if the channel ID is set on the server
        channel_id = guilds[guild]["channel_id"]
        if not channel_id:
            print(f"No channel to send the message on server {guild}.")
            continue
        else:
            channel = bot.get_channel(int(channel_id)) # Check
            if channel is None:
                print(f"Channel {channel} does not exist on server {guild}.")
                continue
            else:
                guild_players_list = guilds[guild]["players_list"]
                if not guild_players_list:
                    print("No players to check.")
                    continue
                else:
                    for player in guild_players_list:
                        puuid = player['puuid']
                        region = player['region']
                        match region:
                            case "eun1":
                                region_routing = "europe"
                            case "euw1":
                                region_routing = "europe"
                            case "na1":
                                region_routing = "americas"

                        # Get the player's match history
                        response = requests.get(f'https://{region_routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?api_key={API_KEY}')
                        match_history = response.json()

                        # Get the last game
                        last_game = match_history[0]

                        # If the last game is the same as the last game in the list, skip the player
                        if last_game == player['last_game']:
                            continue
                        else:
                            player['last_game'] = last_game # Update the player's last game

                            # Get the player last game info and game mode  (Ranked, Normal, Aram)
                            response = requests.get(f'https://{region_routing}.api.riotgames.com/lol/match/v5/matches/{last_game}?api_key={API_KEY}')
                            last_game_mode = response.json()['info']['gameMode']

                            # Check which position in data is the given player
                            response_players = response.json()['metadata']['participants']
                            player_index = response_players.index(puuid)
                            
                            # Using the player index, get the player's stats
                            response_player = response.json()['info']['participants'][player_index] # Get the player's stats
                            
                            # We need to handle the case of some champions having different names in the API
                            # For example, Kog'Maw is KogMaw in the API
                            # We will use a dictionary to map the champion names
                            champion_names = {
                                "KogMaw": "Kog'Maw",
                                "MonkeyKing": "Wukong",
                                "RekSai": "Rek'Sai",
                                "TahmKench": "Tahm Kench",
                                "TwistedFate": "Twisted Fate",
                                "Velkoz": "Vel'Koz",
                                "XinZhao": "Xin Zhao",
                                "AurelionSol": "Aurelion Sol",
                                "Chogath": "Cho'Gath",
                                "DrMundo": "Dr. Mundo",
                                "JarvanIV": "Jarvan IV",
                                "Khazix": "Kha'Zix",
                            }
                            # Check if the champion name is in the dictionary
                            if response_player['championName'] in champion_names:
                                player_champion = champion_names[response_player['championName']]
                            else:
                                player_champion = response_player['championName'] # Get the player's champion
                            

                            # Create a formatted string with the player's stats
                            player_stats = textwrap.dedent(f'''
                            ### NEW GAME FOUND! 
                            Player: **{response_player["summonerName"]}**
                            Game Mode: __{last_game_mode}__
                            Champion: **{player_champion}**
                            Kills: **{response_player['kills']}** | Deaths: **{response_player['deaths']}** | Assists: **{response_player['assists']}**
                            KDA: **{response_player["challenges"]["kda"]:.2f}**
                            DMG: **{response_player['totalDamageDealtToChampions']}**
                            ''')
                            print(player_stats)

                            # Send a message to the Discord channel
                            await channel.send(player_stats)

# Task to backup the database
@tasks.loop(seconds=TIME_BETWEEN_BACKUPS) # Backup every 24 hours
async def backup_database():
    print("Backing up the database...")
    try:
        with open('backup-database.json', 'w') as f:
            json.dump(guilds, f, indent=4)
    except Exception as e:
        print(f"Error while doing backup: {e}")

#Task to save the database
@tasks.loop(seconds=TIME_BETWEEN_SAVE) # Save to database every 5 minutes
async def save_database():
    print("Saving the database...")
    try:
        with open('database.json', 'w') as f:
            json.dump(guilds, f, indent=4)
    except Exception as e:
        print(f"Error while saving the database: {e}")

# Function to check if the player exists
def check_if_player_exists(name, region):
    # Get the player's account ID
    response = requests.get(f'https://{region}.api.riotgames.com/lol/summoner/v4/summoners/by-name/{name}?api_key={API_KEY}')
    if response.status_code == 200:
        return response.json()['puuid']
    else:
        return False

# Function to load the database
def load_database():
    print("Loading the database...")
    try:
        with open('database.json', 'r') as f:
            guilds = json.load(f)
            return guilds
    except Exception as e:
        print(f"Error while loading the database: {e}")

# Event to handle errors when using commands
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Invalid command. Use `!lgs-help` to see available commands.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing arguments. Make sure to provide all required parameters.")
    else:
        print(f"Error: {error}")


guilds = load_database() # Load the database
# Run the bot
bot.run(DISCORD_BOT_TOKEN)
