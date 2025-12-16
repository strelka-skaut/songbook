from enum import StrEnum, auto, Flag
import re
import tempfile
import subprocess
import os
from pick import pick
import json
from slugify import slugify

## User Input Handling ############################################################

def format_all_songs():
    # load songs from songs_with_chords.json
    for song in songs:
        # ask for y/n/a/r
        formatted_song = format_song(song)

class Command(Flag):
    ACCEPT = auto()
    RETRY_PREDICTION_WITH_CHANGES = auto()
    RETRY_PREDICTION_IGNORING_CHANGES = auto()
    ABORT = auto()

def present_to_user(content: str, filename: str = None) -> str:
    """
    Opens the given content in Vim for editing and returns the modified content.
    
    Parameters:
        content (str): The initial content to present to the user.
        filename (str, optional): If provided, use this file instead of a temporary one.
    
    Returns:
        str: The modified content after the user exits Vim.
    """
    # Determine the file to use
    if filename:
        file_path = filename
        # Write initial content to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        # Create a temporary file
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        file_path = tmp_file.name
        tmp_file.write(content.encode('utf-8'))
        tmp_file.close()

    try:
        # Open Vim as a subprocess
        subprocess.run(['nvim', file_path])

        # Read the modified content
        with open(file_path, 'r', encoding='utf-8') as f:
            modified_content = f.read()
    finally:
        # Clean up temporary file if used
        if not filename and os.path.exists(file_path):
            os.remove(file_path)

    return modified_content

## Line prediction ################################################################

class LineType(Flag):
    EMPTY =  auto()
    VERSE =  auto()
    CHORUS = auto()
    CHORDS = auto()
    BRIDGE = auto()
    SOLO =   auto()
    VERSE_WITH_CHORDS =  auto() 
    CHORUS_WITH_CHORDS = auto()
    BRIDGE_WITH_CHORDS = auto() 
    SOLO_WITH_CHORDS =   auto()
    TEXT =   auto()

def predict_line_types(lines):
    line_type_list = []
    for line in lines:
        line_type = LineType.TEXT
        if line.strip() == "":
            line_type = LineType.EMPTY
        elif is_chord_line(line):
            line_type = LineType.CHORDS
        elif (label := get_label(line)) != None:
            if label.isnumeric():
                line_type = LineType.VERSE
            elif 'bridge' in label or '*' in label or 'intro' in label or 'outro' in label:
                line_type = LineType.BRIDGE
            elif 'chorus' in label or 'refren' in label or 'r' in label:
                line_type = LineType.CHORUS
            else:
                line_type = LineType.SOLO
        line_type_list.append(line_type)
    return list(zip(line_type_list, lines))

def is_chord_line(line):
    line = line.lstrip()
    char_count = len(re.sub("\\s", "", line))
    whitespace_count = len(line) - char_count
    basic_chord_count = len(line) - len(re.sub("[A-H]", "", line))
    return whitespace_count > char_count - 4 and char_count - basic_chord_count < 8

def get_label(line):
    parts = re.split("[\\.:]", line)
    if len(parts) <= 1:
        return None
    label = parts[0].strip()
    if re.sub("\\s", "", label) == label:
        return label.lower()
    else: # likely a : that is part of a line
        return None
    
def getGroupName(group_type):
    if group_type in LineType.VERSE | LineType.VERSE_WITH_CHORDS:
        return "verse"
    elif group_type in LineType.CHORUS | LineType.CHORUS_WITH_CHORDS:
        return "refren"
    elif group_type in LineType.BRIDGE | LineType.BRIDGE_WITH_CHORDS:
        return "deco"
    elif group_type in LineType.SOLO | LineType.SOLO_WITH_CHORDS:
        return "solo"
    return ""

def format_annotated_lines(lines):
    chord_buffer = ""

    output_lines = []
    current_group_type = None
    group_lines = []
    group_padding = 0
    merge_chords = False

    def end_group():
        nonlocal group_lines
        nonlocal output_lines
        nonlocal current_group_type
        nonlocal group_padding
        nonlocal merge_chords

        if len(group_lines) > 0:
            base_lines = [line + " \\\\" for line in group_lines[:-1]]
            last_line = group_lines[-1]
            output_lines.extend(base_lines)
            output_lines.append(last_line)
        output_lines.append(f"\\end{{{getGroupName(current_group_type)}}}")
        current_group_type = None
        group_lines = []
        group_padding = 0
        merge_chords = False

    group_start = LineType.VERSE_WITH_CHORDS | LineType.CHORUS_WITH_CHORDS | LineType.BRIDGE_WITH_CHORDS | LineType.SOLO_WITH_CHORDS | LineType.VERSE | LineType.CHORUS | LineType.BRIDGE | LineType.SOLO
    has_chords = LineType.VERSE_WITH_CHORDS | LineType.CHORUS_WITH_CHORDS | LineType.BRIDGE_WITH_CHORDS | LineType.SOLO_WITH_CHORDS
    gobbles_chords = group_start | LineType.TEXT
    should_be_appended = group_start | LineType.TEXT

    for line_type, line in lines:
        if line_type == LineType.EMPTY and current_group_type is not None:
            end_group()
        elif line_type in group_start:
            if current_group_type is not None:
                end_group()

            current_group_type = line_type
            group_padding = get_group_padding_length(line)
            merge_chords = line_type in has_chords
            output_lines.append(f"\\begin{{{getGroupName(current_group_type)}}}")

        if line_type in should_be_appended:
            if current_group_type is None:
                group_padding = len(line) - len(line.lstrip())
                if chord_buffer == "":
                    current_group_type = LineType.VERSE
                else:
                    current_group_type = LineType.VERSE_WITH_CHORDS
                output_lines.append(f"\\begin{{{getGroupName(current_group_type)}}}")
            if current_group_type == LineType.SOLO:
                group_lines.append(format_solo_line(line[group_padding:]))
            elif current_group_type in has_chords:
                group_lines.append(" " * 3 + merge(line[group_padding:], chord_buffer[group_padding:], False))
            else:
                group_lines.append(" " * 3 + merge(line[group_padding:], chord_buffer[group_padding:], True))
        elif line_type == LineType.CHORDS:
            chord_buffer = line
            
        if line_type in gobbles_chords:
            chord_buffer = ""

    if current_group_type is not None:
        end_group()

    return output_lines

def format_chord(chord, is_optional, is_special):
    return "\\" + ('o' if is_optional else 'm') + f"chord{ '*' if is_special else ''}{{{chord}}}"

def format_solo_line(line):
    chords = re.split("\\s", line)
    return " ".join([f"\\inlinechord{{{chord}}}" for chord in chords])

def merge(base, details, are_chords_optional):
    if len(details.strip()) == 0:
        return base
    details = details.rstrip()

    base_length = len(base)
    details_length = len(details)

    # ensure base is longer than chords at least by a character
    if base_length <= details_length:
        base += " " * (details_length - base_length)

    segment_length_list = []
    detail_list = []

    # get shifts
    prev_detail_length = 0
    while details != "":
        left_padding_length = len(details) - len(details.lstrip())
        details = details[left_padding_length:]
        detail = re.split("\\s", details, maxsplit=1)[0]
        detail_length = len(detail)
        details = details[detail_length:]

        detail_list.append(detail)
        segment_length_list.append(prev_detail_length + left_padding_length)

        prev_detail_length = detail_length
    if (last_segment_length := len(base) - sum(segment_length_list)) != 0:
        segment_length_list.append(last_segment_length)

    # setup so that we always add a chord and it's fill as a suffix (not prefix)
    total_segment_length = segment_length_list.pop(0)
    merged = base[:total_segment_length]
    segment_length_list.append(0)
    is_starred = False
    for index, (segment_length, detail) in enumerate(zip(segment_length_list, detail_list)):
        is_last = index == len(detail_list) - 1
        segment = base[total_segment_length:total_segment_length + segment_length]
        segment_space_count = len(re.sub("[^\\s]", "", segment))
        detail_length = max(len(detail) + 1, 3)
        if "m" in detail.lower() or "dim" in detail.lower():
            detail_length += 2
        segment_far_space_count = 0 if detail_length >= len(segment) else len(re.sub("[^\\s]", "", segment[detail_length:]))

        if not is_last and segment_space_count == 0 and len(segment) != 0:
            is_starred = True
            # single word, we need to split it with space and add a star
            if len(segment) >= detail_length:
                segment = segment[:detail_length] + " " + segment[detail_length:]
            else:
                segment += " "

        elif segment_far_space_count > 0:
            # replace spaces until detail length with ~
            if (replaced_count := segment_space_count - segment_far_space_count) != 0:
                segment = re.sub("\\s", "~", segment, count=replaced_count)

        merged += format_chord(detail, are_chords_optional, is_starred)
        # merged += f"^{'*' if is_starred else ''}{{" + detail + "}"
        merged += segment
        total_segment_length += segment_length
        is_starred = False
    return merged

def get_group_padding_length(line):
    # try : < first, then : (and for .)
    if re.search("[\\.:]", line) is None:
        return 0
    return len(re.split("[\\.:]", line, maxsplit=1)[0]) + 2 # assume : < spacing

## Song manipulation ##############################################################

def parse_checked_line_type_predictions(lines):
    """Return a tuple with a particular user command and the clean pairs of line and type"""
    pass

###################################################################################

def format_line_type(line_type):
    match line_type:
        case LineType.EMPTY:
            return "e"
        case LineType.VERSE:
            return "v"
        case LineType.CHORUS:
            return "r"
        case LineType.CHORDS:
            return "c"
        case LineType.BRIDGE:
            return "b"
        case LineType.SOLO:
            return "s"
        case LineType.VERSE_WITH_CHORDS:
            return "V"
        case LineType.CHORUS_WITH_CHORDS:
            return "R"
        case LineType.BRIDGE_WITH_CHORDS:
            return "B"
        case LineType.SOLO_WITH_CHORDS:
            return "S"
        case LineType.TEXT:
            return " "

def parse_line_type(text):
    match text:
        case "e":
            return LineType.EMPTY
        case "v":
            return LineType.VERSE
        case "r":
            return LineType.CHORUS
        case "c":
            return LineType.CHORDS
        case "b":
            return LineType.BRIDGE
        case "s":
            return LineType.SOLO
        case "V":
            return LineType.VERSE_WITH_CHORDS
        case "R":
            return LineType.CHORUS_WITH_CHORDS
        case "B":
            return LineType.BRIDGE_WITH_CHORDS
        case "S":
            return LineType.SOLO_WITH_CHORDS
        case " ":
            return LineType.TEXT

def format_line_annotations(line_annotations):
    output = []
    for line_type, line in line_annotations:
        output.append(f"{format_line_type(line_type)} > {line}")
    return '\n'.join(output)


def process_song(song, use_existing_annotations, use_existing_formatted):
    while True:
        if use_existing_annotations and 'annotated_lines' in song:
            annotated_lines = [(parse_line_type(type_char), line) for type_char, line in song['annotated_lines']]
        else:
            annotated_lines = predict_line_types(song['chords'].splitlines())

        if not use_existing_formatted: # don't need user input since we'll use the already stored formatting anyway
            modified = present_to_user(format_line_annotations(annotated_lines))
            song['annotated_lines'] = [(line[0], line[4:]) for line in modified.splitlines()]

        while True:
            if use_existing_formatted and 'formatted_lines' in song:
                formatted_lines = song['formatted_lines'].splitlines()
            else:
                formatted_lines = format_annotated_lines([(parse_line_type(type_char), line) for type_char, line in song['annotated_lines']])
                formatted_lines.insert(0, "\\begin{song}{}")
                formatted_lines.insert(0, f"\\mysong{{{song['title']}}}{{{song['artist'] + ' ' + song['release_year']}}}{{}}")
                formatted_lines.append("\\end{song}")
                formatted_lines.append("\\pagebreak")


            formatted_lines = present_to_user('\n'.join(formatted_lines), "songs/preview.tex")
            # add to main.tex

            song['formatted_lines'] = formatted_lines



            save = "Save"
            retry_with_changes = "Try formatting again"
            retry_ignoring_changes = "Edit line annotations"
            try_again = "Clear annotation changes and retry"
            cancel = "Clear all edits and cancel"
            
            selection, _ = pick([save, retry_with_changes, retry_ignoring_changes, try_again, cancel], "Next step:")
            with open('songs/preview.tex', 'wt', encoding="utf-8") as preview_file:
                preview_file.write("x\n\\pagebreak\n\n" * 3)

            if selection == save:
                return song
            elif selection == retry_with_changes:
                continue
            elif selection == retry_ignoring_changes:
                use_existing_formatted = False
                use_existing_annotations = True
                break
            elif selection == try_again:
                use_existing_formatted = False
                use_existing_annotations = False
                break
            elif selection == cancel:
                song.pop("annotated_lines", None)
                song.pop("formatted_lines", None)
                return song

def process_song_list():
    with open("song_with_chords.json") as input_file:
        songs = json.load(input_file)
   
    prev_song = None
    index = 0
    song_count = len(songs)
 
    prev_title = ""
    edit = "Format"
    edit_line_types = "Edit line annotations"
    edit_formatted_lines = "Edit formatted lines"
    skip = "Skip"
    retry_previous = "Redo previous"
    stop = "Exit"

    processed_song_list = []
   
    while len(songs) != 0:
        curr_song = songs.pop(0)
        prompt = f"[{index + 1}/{song_count}] {curr_song['title']} ({curr_song['artist']} {curr_song['release_year']}):"

        retry_previous = f"Redo {prev_title}"

        options = [edit, skip]
        if prev_song is not None and False:
            options.append(retry_previous)
        if 'annotated_lines' in curr_song:
            options.append(edit_line_types)
        if 'formatted_lines' in curr_song:
            options.append(edit_formatted_lines)
        options.append(stop)
        default_index = 0
        if os.path.exists(f"songs/{slugify(curr_song['title'])}.tex"):
            default_index = 1


        # show formatted lines in preview if exists
        if 'formatted_lines' in curr_song:
            with open("songs/preview.tex", "w", encoding="utf-8") as preview_file:
                preview_file.write(curr_song['formatted_lines'])

        task, _ = pick(options, prompt, default_index = default_index, indicator=">")

        if task == stop:
            processed_song_list.append(curr_song)
            processed_song_list.extend(songs)
            break

        if task in [edit, edit_line_types, edit_line_types, edit_formatted_lines, skip]:
            prev_title = curr_song['title']
            prev_song = curr_song
            index += 1
            if task == skip:
                if 'formatted_lines' in curr_song:
                    with open(f"songs/{slugify(curr_song['title'])}.tex", "wt", encoding="utf-8") as output_file:
                        output_file.write(curr_song['formatted_lines'])
                processed_song_list.append(curr_song)
                continue
            processed_song = process_song(curr_song, task == edit_line_types, task == edit_formatted_lines)
            if 'formatted_lines' in processed_song:
                with open(f"songs/{slugify(curr_song['title'])}.tex", "wt", encoding="utf-8") as output_file:
                    output_file.write(processed_song['formatted_lines'])
            processed_song_list.append(processed_song)
            prev_song = curr_song

        elif task == retry_previous:
            index -= 1
            tmp_list = []
            while (tmp := processed_song_list.pop()) != prev_song and len(processed_song_list) != 0:
                tmp_list.append(tmp)
            processed_song_list.extend(tmp_list)
            songs.insert(0, prev_song)
            prev_title = ""
            prev_song = None

    with open("song_with_chords.json", "wt", encoding="utf-8") as output_file:
        output_file.write(json.dumps(processed_song_list, indent=3, ensure_ascii=False))

if __name__ == "__main__":
    process_song_list()

