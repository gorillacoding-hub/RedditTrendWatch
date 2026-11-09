RedditTrendWatch

A lightweight Reddit political trend research and monitoring tool.

RedditTrendWatch collects public Reddit posts, analyzes recurring topics, tracks trends across country-based community lists, stores results locally, and provides a local web dashboard.

It is designed to run on Android through Termux, Linux, macOS, and Windows.

Features

- Country-based monitoring: Browse available countries and their suggested subreddit communities.
- Custom subreddit lists: Add communities individually instead of using the default lists.
- Trend analysis: Identify recurring topics and discussions from collected posts.
- Local database: Store collected data locally using SQLite.
- Web dashboard: View research results through a browser.
- CSV export: Export analyzed topics for further research.
- Continuous monitoring: Run repeated collection and analysis using watch mode.
- Lightweight operation: Uses Python and a limited set of public feed requests.
- No Reddit account required: Designed to access public Reddit feeds without logging in or providing Reddit API credentials.

Installation

Android (Termux)

1. Install Termux from "F-Droid" (https://f-droid.org/packages/com.termux/) or the official "Termux GitHub repository" (https://github.com/termux/termux-app).
2. Open Termux.
3. Update packages:

pkg update && pkg upgrade -y

4. Install Python and Git:

pkg install python git -y

5. Clone the repository:

git clone https://github.com/gorillacoding-hub/RedditTrendWatch.git

6. Enter the project directory:

cd RedditTrendWatch

7. Run the tool:

python reddit_trends.py


Linux

Install Python 3 and Git using your distribution's package manager.

For Debian and Ubuntu:

sudo apt update
sudo apt install python3 git -y

Clone and enter the repository:

git clone https://github.com/gorillacoding-hub/RedditTrendWatch.git
cd RedditTrendWatch

Run:

python3 reddit_trends.py

macOS

Install Python 3 and Git. You can use "Homebrew" (https://brew.sh/):

brew install python git

Clone the project:

git clone https://github.com/gorillacoding-hub/RedditTrendWatch.git
cd RedditTrendWatch

Run:

python3 reddit_trends.py

Windows

1. Install Python 3 from "python.org" (https://www.python.org/downloads/).
2. Install Git from "git-scm.com" (https://git-scm.com/downloads).
3. Open PowerShell.
4. Clone the repository:

git clone https://github.com/gorillacoding-hub/RedditTrendWatch.git
cd RedditTrendWatch

5. Run:

py reddit_trends.py

Usage

RedditTrendWatch uses command-based operation.

To display the available commands:

python reddit_trends.py

Available commands

Command| Description
"serve"| Start the local web dashboard.
"run"| Collect posts, analyze trends, and save results.
"collect"| Collect posts without running analysis.
"analyze"| Analyze previously collected posts.
"watch"| Repeat collection and analysis at regular intervals.
"export"| Export current topics to a CSV file.
"add"| Add subreddit communities individually and save a list.
"lists"| Display saved subreddit lists.
"countries"| Display available countries and their communities.

1. Start the dashboard

python reddit_trends.py serve

Open your browser and visit:

http://127.0.0.1:8765

The dashboard runs locally on your device.

Keep Termux or the terminal session running while using the dashboard.

run it from the dashboard(better) or use commands :

2. Collect and analyze trends

python reddit_trends.py run

This performs the collection and analysis workflow.

3. Collect posts only

python reddit_trends.py collect

Use this when you want to gather data first and analyze it later.

4. Analyze previously collected data

python reddit_trends.py analyze

5. Monitor trends continuously

python reddit_trends.py watch

Watch mode repeats the research workflow. Use the command's help output to inspect supported interval options:

python reddit_trends.py watch --help

6. Select country communities

python reddit_trends.py countries

This displays the available country profiles and their suggested communities.

7. Add custom subreddits

python reddit_trends.py add

Follow the interactive prompts to enter subreddit names individually and save your custom list.

8. View saved lists

python reddit_trends.py lists

9. Export research results

python reddit_trends.py export

Use the command's help output to inspect any supported export options:

python reddit_trends.py export --help

Android Storage

To allow Termux to access shared Android storage:

termux-setup-storage

Grant the requested Android storage permission.

The shared Downloads directory is available through:

~/storage/downloads/

To copy the complete project folder into Android Downloads:

cp -a ~/RedditTrendWatch ~/storage/downloads/

Data and Privacy

RedditTrendWatch is designed for local research and minimal data collection.

- No Reddit account login is required.
- No Reddit password or API key is required for the public-feed workflow.
- Research data is stored locally in an SQLite database.
- Public posts are used as research input.
- The tool does not need access to device contacts, phone numbers, SMS, or call history.
- The dashboard is intended for local access through "127.0.0.1".
- Network requests are made to retrieve public Reddit feed information.

Network note: Access to public feeds still sends requests to the feed provider. Review the source code before use if you need to audit network destinations and exactly which fields are stored.

Data Storage

The project uses a local SQLite database to preserve collected posts and research results.

The database is stored in the project directory. Keep the database file if you want to retain historical research between sessions.

Back up the project directory periodically if the collected data is important.

Troubleshooting

Python is not installed

Android Termux:

pkg install python -y

Linux:

sudo apt install python3 -y

The dashboard does not open

Make sure the dashboard process is running:

python reddit_trends.py serve

Then open:

http://127.0.0.1:8765

Do not close the terminal session running the server.

Address already in use

If port "8765" is already occupied, check whether another dashboard instance is running. Stop the previous instance before starting another one.

Permission denied on Android

Run:

termux-setup-storage

Then grant storage permission in Android settings if prompted.

No posts are collected

Possible causes include:

- The subreddit does not exist.
- The subreddit is private or restricted.
- Reddit is temporarily limiting requests.
- Your network connection is unavailable.
- The public feed is temporarily inaccessible.

Try another public subreddit and run the collection command again.

Updating

To update an existing Git installation:

cd RedditTrendWatch
git pull

Back up your database before updating the project.

Requirements

- Python 3
- Internet connection
- Git (for installation and updates)
- A web browser (for the dashboard)
- Available storage for the local database

The tool is intended to use Python's standard library for its core operations.

License

See the repository's license file for the applicable licensing terms.

Project

RedditTrendWatch

GitHub: https://github.com/gorillacoding-hub/RedditTrendWatch

Issues and contributions: https://github.com/gorillacoding-hub/RedditTrendWatch/issues

---
