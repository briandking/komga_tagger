# Komga Tagger

A Python script to fetch book metadata from a Komga server and inject it into a CBZ comic archive as a `ComicInfo.xml` file.
This allows for better metadata portability when using multiple comic readers that support `ComicInfo.xml`.

## Prerequisites

- Python 3.13+
- `requests` library (install with `pip install requests`)

## Usage

```bash
python komga_tagger.py <cbz_path> [options]
```

### Options

| Option | Description |
| :--- | :--- |
| `--url` | Komga server URL (default: `http://localhost:25600`) |
| `-u`, `--username` | Komga username/email |
| `-p`, `--password` | Komga password |
| `-k`, `--api-key` | Komga API Key |
| `-n`, `--dry-run` | Only preview changes without writing them |
| `-o`, `--overwrite` | Overwrite existing `ComicInfo.xml` file without warning |
| `-v`, `--verbose` | Display the generated `ComicInfo.xml` content |

### Example

Using an API Key:
```bash
python komga_tagger.py "My Comic.cbz" --api-key YOUR_API_KEY
```

Using username/password:
```bash
python komga_tagger.py "My Comic.cbz" --url http://your-komga-server:port -u username -p password
```

## How it works

1. Queries the Komga API for the book using the filename.
2. Retrieves metadata for the book and its series.
3. Generates a standard `ComicInfo.xml` structure from the Komga metadata.
4. Injects the `ComicInfo.xml` into the root of the CBZ archive, removing any existing one (if `--overwrite` is specified).
