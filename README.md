# TCT - Transformer Circuits Tracker

An unofficial RSS feed generator for [Transformer Circuits](https://transformer-circuits.pub/), a research publication from Anthropic's Interpretability team.

## Overview

This project automatically scrapes the Transformer Circuits website and generates an RSS feed, making it easy to stay updated with the latest mechanistic interpretability research without manually checking the website.

The RSS feed is automatically updated daily via GitHub Actions and hosted on GitHub Pages.

## Features

- **Automatic Updates**: RSS feed refreshes daily at 06:17 UTC via GitHub Actions
- **Complete Coverage**: Captures all articles including research papers and circuit updates
- **Clean Content**: Handles UTF-8 encoding properly, avoiding mojibake characters
- **Metadata Rich**: Includes publication dates, descriptions, and proper titles
- **Sorted by Date**: Articles are ordered newest-first for easy consumption

## RSS Feed URL

Subscribe to the feed at: `https://dschaehi.github.io/TCT/index.xml`

You can use any RSS reader to subscribe to this feed.

## Local Usage

### Prerequisites

- Python 3.11 or higher
- pip package manager

### Installation

1. Clone the repository:
```bash
git clone https://github.com/dschaehi/TCT.git
cd TCT
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Generate the RSS Feed

Run the feed generator script:
```bash
python scripts/generate_feed.py
```

This will create/update the RSS feed at `docs/index.xml`.

## How It Works

The script (`scripts/generate_feed.py`):
1. Fetches the homepage of transformer-circuits.pub
2. Extracts all article links (both `.note` cards and `.paper` elements)
3. For each article, retrieves metadata including publication dates
4. Generates a properly formatted RSS 2.0 feed with all discovered articles
5. Saves the output to `docs/index.xml`

The GitHub Actions workflow (`.github/workflows/rss.yml`):
- Runs daily on a schedule
- Executes the feed generator
- Commits and pushes any updates to the feed

## Dependencies

- [beautifulsoup4](https://pypi.org/project/beautifulsoup4/) - HTML parsing
- [requests](https://pypi.org/project/requests/) - HTTP requests
- [feedgen](https://pypi.org/project/feedgen/) - RSS feed generation
- [lxml](https://pypi.org/project/lxml/) - XML processing

## Contributing

Contributions are welcome! Feel free to:
- Report bugs or issues
- Suggest improvements
- Submit pull requests

## License

MIT License - see [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Jae Hee Lee

## Disclaimer

This is an **unofficial** RSS feed. The content is sourced from [transformer-circuits.pub](https://transformer-circuits.pub/), which is maintained by Anthropic's Interpretability team. This project is not affiliated with or endorsed by Anthropic.

## Acknowledgments

- Thanks to the Anthropic Interpretability team for publishing their research at transformer-circuits.pub
- This project helps researchers and enthusiasts stay updated with the latest developments in mechanistic interpretability
