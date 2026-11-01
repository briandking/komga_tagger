import os
import sys
import argparse
import zipfile
import tempfile
import requests
import xml.etree.ElementTree as ET
import xml.dom.minidom


def get_komga_session(username=None, password=None, api_key=None):
    session = requests.Session()
    if api_key:
        session.headers.update({"X-API-KEY": api_key})
    elif username and password:
        session.auth = (username, password)
    else:
        raise ValueError("Authentication credentials not provided")
    return session


def find_book_in_komga(komga_url, session, filename):
    # Search for the book by filename in Komga
    search_url = f"{komga_url}/api/v1/books"
    response = session.get(search_url, params={"search": filename})
    response.raise_for_status()
    data = response.json()
    
    books = data.get("content", [])
    if not books:
        # Fallback: search without file extension if exact match fails
        base_name = os.path.splitext(filename)[0]
        response = session.get(search_url, params={"search": base_name})
        response.raise_for_status()
        books = response.json().get("content", [])
        
    if not books:
        print(f"Error: Could not find book matching '{filename}' in Komga database.")
        sys.exit(1)
        
    book = books[0]
    return book["id"], book.get("seriesId")


def get_book_metadata(komga_url, session, book_id, series_id):
    # Fetch book and series details from Komga REST API
    book_res = session.get(f"{komga_url}/api/v1/books/{book_id}")
    book_res.raise_for_status()
    book_data = book_res.json()
    
    series_res = session.get(f"{komga_url}/api/v1/series/{series_id}")
    series_res.raise_for_status()
    series_data = series_res.json()
    
    return book_data, series_data


def build_comic_info_xml(book_data, series_data):
    root = ET.Element("ComicInfo")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    
    meta = book_data.get("metadata", {})
    series_meta = series_data.get("metadata", {})
    
    def add_field(tag, text):
        if text is not None and str(text).strip() != "":
            elem = ET.SubElement(root, tag)
            elem.text = str(text)

    # Core comic metadata mapping
    add_field("Title", meta.get("title"))
    add_field("Series", series_data.get("name"))
    add_field("Number", meta.get("number"))
    add_field("Summary", meta.get("summary"))
    add_field("Publisher", series_meta.get("publisher"))
    add_field("AgeRating", series_meta.get("ageRating"))
    add_field("LanguageISO", series_meta.get("language"))
    
    # Release date parsing
    release_date = meta.get("releaseDate")
    if release_date:
        parts = release_date.split("-")
        if len(parts) >= 1: add_field("Year", parts[0])
        if len(parts) >= 2: add_field("Month", parts[1])
        if len(parts) >= 3: add_field("Day", parts[2])

    # Authors mapping (Komga roles to ComicInfo roles)
    authors = meta.get("authors", [])
    role_map = {
        "writer": "Writer",
        "penciller": "Penciller",
        "inker": "Inker",
        "colorist": "Colorist",
        "letterer": "Letterer",
        "cover": "CoverArtist",
        "editor": "Editor"
    }
    
    for komga_role, xml_tag in role_map.items():
        names = [a["name"] for a in authors if a.get("role") == komga_role]
        if names:
            add_field(xml_tag, ", ".join(names))

    # Beautify XML output
    rough_string = ET.tostring(root, encoding="utf-8")
    reparsed = xml.dom.minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="utf-8")


def inject_xml_into_cbz(cbz_path, xml_bytes, dry_run=False, overwrite=False):
    # Check for existing ComicInfo.xml
    with zipfile.ZipFile(cbz_path, 'r') as zin:
        exists = any(item.filename.lower() == "comicinfo.xml" for item in zin.infolist())

    if exists and not overwrite:
        if dry_run:
            print(f"Warning: ComicInfo.xml already exists in {cbz_path}. Would have overwritten it (use --overwrite to force).")
            return
        else:
            print(f"Error: ComicInfo.xml already exists in {cbz_path}. Use --overwrite to replace it.")
            sys.exit(1)

    if dry_run:
        print(f"Dry run: Skipping archive update for {cbz_path}.")
        return

    # Use a temporary file to safely write the updated archive in the same directory as the target
    temp_fd, temp_path = tempfile.mkstemp(suffix=".cbz", dir=os.path.dirname(os.path.abspath(cbz_path)))
    os.close(temp_fd)
    
    try:
        with zipfile.ZipFile(cbz_path, 'r') as zin, zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                # Drop any existing ComicInfo.xml to avoid duplicates
                if item.filename.lower() == "comicinfo.xml":
                    continue
                zout.writestr(item, zin.read(item.filename))
            
            # Inject new metadata file at the root
            zout.writestr("ComicInfo.xml", xml_bytes)
        
        # Overwrite original archive: handle cross-device move by reading/writing
        # os.replace fails when source and destination are on different filesystems
        if os.path.exists(cbz_path) and os.path.samefile(temp_path, cbz_path) == False:
            # Read from temp file and write to target
            with open(temp_path, 'rb') as f:
                content = f.read()
            # Open target in append+ mode to overwrite, preserving file size
            with open(cbz_path, 'wb') as f:
                f.write(content)
        else:
            # Fallback to os.replace when possible
            os.replace(temp_path, cbz_path)
        
        print(f"Successfully embedded ComicInfo.xml into: {cbz_path}")
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise e


def main():
    parser = argparse.ArgumentParser(description="Embed Komga metadata into a CBZ comic archive.")
    parser.add_argument("cbz_path", help="Path to the comic.cbz file")
    parser.add_argument("--url", default="http://localhost:25600", help="Komga server URL (default: http://localhost:25600)")
    parser.add_argument("-u", "--username", help="Komga username/email")
    parser.add_argument("-p", "--password", help="Komga password")
    parser.add_argument("-k", "--api-key", help="Komga API Key")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Only preview changes without writing them")
    parser.add_argument("-o", "--overwrite", action="store_true", help="Overwrite existing ComicInfo.xml file without warning")
    parser.add_argument("-v", "--verbose", action="store_true", help="Display the generated ComicInfo.xml content")

    args = parser.parse_args()

    if not args.api_key and not (args.username and args.password):
        parser.error("Either --api-key OR both --username and --password must be provided.")

    cbz_path = args.cbz_path
    if not os.path.exists(cbz_path):
        print(f"Error: File '{cbz_path}' does not exist.")
        sys.exit(1)

    filename = os.path.basename(cbz_path)
    print(f"Target file: {filename}")

    try:
        session = get_komga_session(username=args.username, password=args.password, api_key=args.api_key)
    except ValueError as e:
        print(f"Authentication Error: {e}")
        sys.exit(1)

    komga_url = args.url.rstrip("/")

    print("Querying Komga API...")
    book_id, series_id = find_book_in_komga(komga_url, session, filename)

    print("Retrieving book & series metadata...")
    book_data, series_data = get_book_metadata(komga_url, session, book_id, series_id)

    print("Generating ComicInfo.xml...")
    xml_bytes = build_comic_info_xml(book_data, series_data)

    if args.verbose:
        print("--- Generated ComicInfo.xml ---")
        print(xml_bytes.decode('utf-8'))
        print("-------------------------------")

    print("Updating archive...")
    inject_xml_into_cbz(cbz_path, xml_bytes, args.dry_run, args.overwrite)
    print("Done! You can now trigger a metadata refresh in Komga.")


if __name__ == "__main__":
    main()
