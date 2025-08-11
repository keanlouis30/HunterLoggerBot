import discord
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os

# --- Discord Bot Setup ---
# It's safer to get the token from an environment variable
BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN')

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)

# --- Google Sheets Setup ---
# Check if the credentials file exists
if not os.path.exists('credentials.json'):
    print("Error: credentials.json not found! Please create it in the same directory.")
    exit()

# Use creds to create a client to interact with the Google Drive API
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    gspread_client = gspread.authorize(creds)

    # Make sure you use the right name here.
    # Replace "Your Google Sheet Name" with the actual name of your sheet.
    sheet = gspread_client.open("Hunter_Logging").sheet1
except Exception as e:
    print(f"An error occurred with Google Sheets authentication: {e}")
    print("Please ensure your credentials.json is correct and you have shared the sheet with the client_email.")
    exit()


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    # Add headers to the sheet if it's empty (has no cells with values)
    if not sheet.get_all_values():
        try:
            sheet.append_row(['Username', 'User ID', 'Roles', 'Action', 'Timestamp (UTC)'])
            print("Set up headers in the Google Sheet.")
        except Exception as e:
            print(f"Failed to set up headers: {e}")


@client.event
async def on_message(message):
    # Ignore messages sent by the bot itself
    if message.author == client.user:
        return

    # Process login command
    if message.content.lower() == '@loggingin':
        user = message.author
        # Get role names, excluding the default "@everyone" role
        roles = [role.name for role in user.roles if role.name != "@everyone"]
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        print(f"Logging in user: {user.name}")
        try:
            row_to_add = [user.name, str(user.id), ', '.join(roles), 'Login', timestamp]
            sheet.append_row(row_to_add)
            await message.channel.send(f'Welcome, {user.mention}! Your login has been recorded.')
        except Exception as e:
            await message.channel.send(f"Sorry, I couldn't log that to the sheet. Error: {e}")
            print(f"Error writing to sheet: {e}")


    # Process logout command
    if message.content.lower() == '@logout':
        user = message.author
        roles = [role.name for role in user.roles if role.name != "@everyone"]
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        print(f"Logging out user: {user.name}")
        try:
            row_to_add = [user.name, str(user.id), ', '.join(roles), 'Logout', timestamp]
            sheet.append_row(row_to_add)
            await message.channel.send(f'Goodbye, {user.mention}! Your logout has been recorded.')
        except Exception as e:
            await message.channel.send(f"Sorry, I couldn't log that to the sheet. Error: {e}")
            print(f"Error writing to sheet: {e}")

# Final check for the token
if BOT_TOKEN is None:
    print("Error: The environment variable DISCORD_BOT_TOKEN is not set.")
    print("Please set it using: export DISCORD_BOT_TOKEN='your_token_here'")
else:
    try:
        client.run(BOT_TOKEN)
    except discord.errors.LoginFailure:
        print("Error: Login failed. The bot token is likely incorrect.")