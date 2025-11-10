import re
import json
import tempfile
import subprocess
from typing import List, Optional, Tuple


def predict_label(line: str, separator: str)-> Tuple[str, str]:
    label = line.split(separator)[0].strip().lower()
    if label in ["r", "refren", "ref", "chorus", "chor"]:
        return ('r', line)
    elif label in [str(i) for i in range(10)]:
        return ('v', line)
    elif label in ["intro", "outro", "bridge"]:
        return (label[0], line)
    else:
        return (' ', line)


def predict_line_types(lines: List[str]) -> List[Tuple[Optional[str], str]]:
    prediction = []

    for line in lines:
        # first check for empty line, then chords, then label, then empty
        if line.strip() == "":
            prediction.append(('e', line))
        elif is_chord_line(line):
            prediction.append(('c', line))
        elif ':' in line:
            prediction.append(predict_label(line, ':'))
        elif '.' in line:
            prediction.append(predict_label(line, '.'))
        else:
            prediction.append((' ', line))
 
    return prediction

def annotate_lines_with_char(lines: List[str]) -> List[Tuple[Optional[str], str]]:
    """
    Opens a vim buffer showing each line prefixed by ' > ' where the user
    can replace the first space with exactly one character.
    
    Format in editor:
        <char or space> > <original text>

    Returns a list of tuples: (char_or_None, original_line)
    """

    # Create text to present in the editor
    # format: "  > <line>"
    line_prediction = predict_line_types(lines)
    text = "\n".join(f"{prediction} > {line}" for prediction, line in line_prediction)

    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tf:
        tmp_path = tf.name
        tf.write(text)
        tf.flush()

    # Launch vim
    subprocess.run(["vim", tmp_path])

    # Parse results
    out: List[Tuple[Optional[str], str]] = []
    with open(tmp_path, "r") as f:
        edited_lines = f.read().splitlines()

    for original, edited in zip(lines, edited_lines):
        # Expect format "<char> > <original>"
        # The annotation slot is edited[0]
        if len(edited) >= 3 and edited[2:4] == "> ":
            c = edited[0]
            if c == " ":
                out.append((None, original))
            else:
                out.append((c, original))
        else:
            # malformed → treat as None
            out.append((None, original))

    return out

def insert_chords_to_line(chords, line):
  
  chords_left = chords
  tmp_line = line + (abs(len(line) - len(chords)) + 1) * " "
  cursor_pos = 0

  line_segments = []
  candidate_segments = []

  while chords_left != "":
    
    chord_shift = len(chords_left) - len(chords_left.lstrip())
    
    chords_left = chords_left.lstrip() 
    chord = re.split(r"\s", chords_left, maxsplit = 1)[0]
    chord_length = len(chord)
    chords_left = chords_left[chord_length:] 

    cursor_pos += chord_shift

    upcoming_cord_shift = len(chords_left) - len(chords_left.lstrip())
    upcoming_line = tmp_line[cursor_pos:cursor_pos + 1 + upcoming_cord_shift]
    if len(chords_left) == 0:
      upcoming_line = tmp_line[cursor_pos:]
    
    
    if ' ' in upcoming_line:
      new_content = "^{" + chord + "}"
      tmp_line = tmp_line[:cursor_pos] + new_content + tmp_line[cursor_pos:]
      cursor_pos += len(new_content) + 1
    else:
      new_content = "^*{" + chord + "}"
      pre_added_space_len = min(len(chord) + 1, len(upcoming_line))
      tmp_line = tmp_line[:cursor_pos] + new_content + tmp_line[cursor_pos:cursor_pos + pre_added_space_len]  + " " + tmp_line[cursor_pos + pre_added_space_len:]
      cursor_pos += len(new_content) + 1 + 1 # +1 for the extra space

    if ' ' in upcoming_line:
      while (index := tmp_line.find(" ", cursor_pos, cursor_pos + len(chord) + 1)) > 0: # heuristics for length
        tmp_line = tmp_line[:index] + "~" + tmp_line[index + 1:]

  return tmp_line.rstrip()

def format_annotated_lines(annotated_lines: List[Tuple[Optional[str], str]]):
  """get rid of padding before verses and so on, and remove redundant chords"""
  output_lines = []

  ignore_chords = True
  chord_line_buffer = ""
  prefix_length = 0
  is_in_verse = False

  for i in range(len(annotated_lines)):
    curr_type, curr_line = annotated_lines[i]
  
    if curr_type != None and curr_type.lower() in ['v', 'r', 'i', 'o', 'b']:
      prefix_length = len(re.split('[\\.:]', curr_line)[0]) + 2 # mad heuristic
      is_in_verse = True
      ignore_chords = curr_type.islower()

      if ignore_chords:
        output_lines.append(curr_line[prefix_length:])
      else:
        output_lines.append(insert_chords_to_line(chord_line_buffer[prefix_length:], curr_line[prefix_length:]))

    elif curr_type == "e": 
      is_in_verse = False
      prefix_length = 0
      pass

    elif curr_type == "c":
      chord_line_buffer = curr_line
    
    elif curr_type is None:
      if ignore_chords:
        output_lines.append(curr_line[prefix_length:])
      else:
        output_lines.append(insert_chords_to_line(chord_line_buffer[prefix_length:], curr_line[prefix_length:]))

    continue 





    if curr_type == 'e':
      if chord_line_buffer != "":
        output_lines.append(curr_line) # a trailing line of chords, should be handled explicitely
      chord_line_buffer = ""
      is_in_verse = False
      prefix_length = 0
      ignore_chords = True
 
    elif curr_type == 'c':
      if is_in_verse == False:
        output_lines.append(chord_line_buffer[prefix_length:])
      chord_line_buffer = curr_line
      continue

    elif curr_type != None and curr_type.isupper():
      if is_in_verse == False:
        output_lines.append(chord_line_buffer[prefix_length:])
      ignore_chords = False
      is_in_verse = True
      prefix_length = len(re.split('[.:]', curr_line)) + 1 # mad heuristic
      output_lines.append(insert_chords_to_line(chord_line_buffer[prefix_length:], curr_line[prefix_length:]))

    elif curr_type == "":
      if is_in_verse == False:
        output_lines.append(chord_line_buffer[prefix_length:])
      if ignore_chords:
        output_lines.append(curr_line[prefix_length:])
      else:
        output_lines.append(insert_chords_to_line(chord_line_buffer[prefix_length:], curr_line[prefix_length:]))
    
    print("==========================\n" + "\n".join(output_lines))
  return output_lines
    
    

def is_chord_line(line: str):
  total_length = len(line)
  if total_length == 0:
    return False
  whitespace_count = len(re.findall(r'\s', line))
  basic_chord_count = len(re.findall(r'[A-H]', line))
  fraction = whitespace_count / total_length
  return fraction > 0.3 and basic_chord_count >= 1


def chords_2_latex(content: str):
  """Add chords to lines below in latex style"""

  label = None
  chords = [] 

  annotated_lines = annotate_lines_with_char(content.splitlines())

  formatted_lines = format_annotated_lines(annotated_lines)

  print("\n".join(formatted_lines))
  return

  for line in content.splitlines():
    is_chords = is_chord_line(line)
    print(("X" if is_chords else " ") + " | " + line)
    


def main():
  with open("song_with_chords.json") as input_file:
    songs = json.load(input_file)
  for song in songs:
    song['latex_chords'] = chords_2_latex(song['chords'])



if __name__ == "__main__":
  main()
