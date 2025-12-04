import json

def fix_metadata(old_metadata):
    new_metadata = []
    for entry in old_metadata:
        year = input(f"{entry['title']} year: ")
        new_entry = entry.copy()  # Copy existing data
        new_entry['year'] = year  # Update/add year
        new_metadata.append(new_entry)
    return new_metadata

def main():
  with open("song_metadata.json") as input_file:
    metadata = json.load(input_file)

  fixed_metadata = fix_metadata(metadata)
  with open("song_metadata_fixed.json", "wt") as output_file:
    output_file.write(json.dumps(fixed_metadata))

if __name__ == "__main__":
  main()
