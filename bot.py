import os
import asyncio
import pandas as pd
import discord
from discord.ext import tasks, commands
from dotenv import load_dotenv
from jobspy import scrape_jobs

# Load credentials from .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID")) if os.getenv("CHANNEL_ID") else None

# Search queries for fresh AI/ML/DS internships
KEYWORDS = [
    "machine learning intern", 
    "ai intern", 
    "data science intern", 
    "research intern machine learning",
    "deep learning intern"
]

# Exclude permanent non-internship roles
EXCLUDE_TERMS = ["senior", "lead", "principal", "manager", "full-time", "staff"]

# Store processed jobs in memory to avoid duplicate alerts
seen_job_ids = set()

# Initialize Discord bot with default intents
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def fetch_fresh_jobs():
    """Scrapes major public job boards (LinkedIn, Indeed, ZipRecruiter) for US AI/ML internships posted within the last hour."""
    all_jobs = []
    
    # Cycle through keywords to stay within search limits
    for query in KEYWORDS[:2]:
        try:
            jobs = scrape_jobs(
                site_name=["linkedin", "indeed", "zip_recruiter"],  # Scrapes LinkedIn + major boards
                search_term=query,
                location="United States",
                results_wanted=10,
                hours_old=1,  # Strictly query jobs posted within the last 1 hour
                country_usa=True
            )

            if isinstance(jobs, pd.DataFrame) and not jobs.empty:
                for _, row in jobs.iterrows():
                    title = str(row.get("title", "")).lower()
                    job_url = str(row.get("job_url", ""))
                    job_id = str(row.get("id", "")) or job_url
                    company = str(row.get("company", "Company N/A"))
                    location = str(row.get("location", "USA / Remote"))
                    site = str(row.get("site", "Job Board")).title()

                    # Ensure the role is an internship and not a senior/full-time position
                    is_intern = "intern" in title
                    is_not_senior = not any(term in title for term in EXCLUDE_TERMS)

                    if is_intern and is_not_senior and job_url:
                        all_jobs.append({
                            "id": job_id,
                            "title": row.get("title"),
                            "company": company,
                            "location": location,
                            "site": site,
                            "url": job_url
                        })
        except Exception as e:
            print(f"Error fetching jobs for query '{query}': {e}")
            
    return all_jobs


@tasks.loop(minutes=5)  # Runs every 5 minutes to deliver instant alerts
async def check_jobs():
    """Background task checking for immediate new drops."""
    if not CHANNEL_ID:
        print("Error: CHANNEL_ID is not set in your .env file.")
        return

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Error: Could not find channel with ID {CHANNEL_ID}")
        return

    print("Checking for fresh AI/ML internships posted in the last hour...")
    latest_jobs = fetch_fresh_jobs()
    
    posted_count = 0
    for job in latest_jobs:
        job_id = job.get("id")
        
        # Check against local cache to post only unseen openings
        if job_id and job_id not in seen_job_ids:
            seen_job_ids.add(job_id)
            posted_count += 1

            # Format Discord notification embed
            embed = discord.Embed(
                title=f"⚡ FAST APPLY: {job['title']}",
                url=job['url'],
                color=discord.Color.green()
            )
            embed.add_field(name="Company", value=job['company'], inline=True)
            embed.add_field(name="Location", value=job['location'], inline=True)
            embed.add_field(name="Source", value=job['site'], inline=True)
            embed.set_footer(text="Posted within the last hour — apply immediately!")

            await channel.send(embed=embed)
            await asyncio.sleep(2)  # Short delay between messages to respect Discord rate limits

    if posted_count > 0:
        print(f"Sent {posted_count} fresh job alerts to Discord.")


@bot.event
async def on_ready():
    print(f"Logged in successfully as {bot.user.name}")
    if not check_jobs.is_running():
        check_jobs.start()


if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN is missing in your .env file.")
    else:
        bot.run(TOKEN)