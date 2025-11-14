import re
import json
import tempfile
import subprocess
import os.path
from typing import List, Optional, Tuple
from slugify import slugify


def predict_label(line: str, separator: str)-> Tuple[str, str]:
    label = line.split(separator)[0].strip().lower()
    if label in ["r", "refren", "ref", "chorus", "chor"]:
        return ('r', line)
    elif label in [str(i) for i in range(10)]:
        return ('v', line)
    elif label in ["*", "intro", "outro", "bridge"]:
        return ('d', line)
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

    for edited in edited_lines:
        # Expect format "<char> > <original>"
        # The annotation slot is edited[0]
        if len(edited) >= 3 and edited[2:4] == "> ":
            c = edited[0]
            if c == " ":
                out.append((None, edited))
            else:
                out.append((c, edited))
        else:
            # malformed → treat as None
            print(f"WARNING: malformed line >{edited}<")
            out.append((None, edited))

    return out

def user_check(song):

    head_lines = ["\\begin{song}{}", f"\\mysong{{{song['title']}}}{{{song['artist'] + ' ' + song['release_year']}}}{{1/0}}"]
    lines = [*head_lines, *song['latex'], "\\end{song}", "\\pagebreak"]

    text = "\n".join(lines)
    path = "songs/" + slugify(song['title']) + ".tex"
    with open(path, "w+") as tf:
        tmp_path = tf.name
        tf.write(text)
        tf.flush()

    # Launch vim
    subprocess.run(["vim", path])

def insert_chords_to_line(chords, line):
  chords_left = chords
  tmp_line = line + (abs(len(line) - len(chords)) + 1) * " "
  cursor_pos = 0

  line_segments = []
  candidate_segments = []

  chord_length = 0
  while chords_left != "":
    chord_shift = len(chords_left) - len(chords_left.lstrip()) + chord_length
    
    chords_left = chords_left.lstrip() 
    chord = re.split(r"\s", chords_left, maxsplit = 1)[0]
    chord_length = len(chord)
    chords_left = chords_left[chord_length:] 

    cursor_pos += chord_shift

    upcoming_cord_shift = len(chords_left) - len(chords_left.lstrip()) + chord_length
    upcoming_line = tmp_line[cursor_pos:cursor_pos + upcoming_cord_shift]
    if len(chords_left) == 0:
      upcoming_line = tmp_line[cursor_pos:]
    
    
    if ' ' in upcoming_line:
      new_content = "^{" + chord + "}"
      tmp_line = tmp_line[:cursor_pos] + new_content + tmp_line[cursor_pos:]
      cursor_pos += len(new_content)
    else:
      new_content = "^*{" + chord + "}"
      pre_added_space_len = min(len(chord) + 1, len(upcoming_line))
      tmp_line = tmp_line[:cursor_pos] + new_content + tmp_line[cursor_pos:cursor_pos + pre_added_space_len]  + " " + tmp_line[cursor_pos + pre_added_space_len:]
      cursor_pos += len(new_content) # +1 for the extra space

    if ' ' in upcoming_line:
      if upcoming_line.strip() != "": # don't do ~ heuristics for blank lines
        while (index := tmp_line.find(" ", cursor_pos, cursor_pos + len(chord) + 1)) > 0: # heuristics for length
          if ' ' not in tmp_line[index + 1:]:
            break # KISS
          else:
            tmp_line = tmp_line[:index] + "~" + tmp_line[index + 1:]

  return tmp_line.rstrip()

def format_annotated_lines(annotated_lines: List[Tuple[Optional[str], str]]):
  """get rid of padding before verses and so on, and remove redundant chords"""
  output_lines = []

  ignore_chords = True
  chord_line_buffer = ""
  prefix_length = 4
  is_in_verse = False
  verse_type = ""

  for i in range(len(annotated_lines)):
    curr_type, curr_line = annotated_lines[i]
  
    if curr_type != None and curr_type.lower() in ['v', 'r', 'd']:
      if ('.' not in curr_line[:min(len(curr_line),10)]) and (':' not in curr_line):
        prefix_length = 4 # the 'c > '
      else:
        prefix_length = len(re.split('[\\.:]', curr_line)[0]) + 2 # mad heuristic
      is_in_verse = True
      ignore_chords = curr_type.islower()

      if curr_type.lower() == "v":
        verse_type = "verse"
      elif curr_type.lower() == "r":
        verse_type = "refren"
      elif curr_type.lower() == "d":
        verse_type = "deco"
      else:
        verse_type = "undefined"
      output_lines.append("\\begin{" + verse_type + "}")

      if ignore_chords:
        output_lines.append(" " * 3 + curr_line[prefix_length:] + " \\\\")
      else:
        output_lines.append(" " * 3 + insert_chords_to_line(chord_line_buffer[prefix_length:], curr_line[prefix_length:]) + " \\\\")

    elif curr_type == "e": 
      if is_in_verse:
        last_line = output_lines.pop()
        if last_line.endswith("\\\\"):
          last_line = re.sub(r"\\\\$", "", last_line)
        output_lines.append(last_line)
        output_lines.append("\\end{" + verse_type + "}")
      elif ignore_chords == False:
        output_lines.append(chord_line_buffer[prefix_length:])
      verse_type = "" 
      is_in_verse = False
      ignore_chords = True
      prefix_length = 4 # see above
      pass

    elif curr_type != None and curr_type.lower() == "c":
      if curr_type.isupper():
        ignore_chords = False
      chord_line_buffer = curr_line
    
    elif curr_type is None:
      if ignore_chords:
        output_lines.append(" " * 3 + curr_line[prefix_length:] + " \\\\")
      else:
        output_lines.append(" " * 3 + insert_chords_to_line(chord_line_buffer[prefix_length:], curr_line[prefix_length:]) + " \\\\")

  if verse_type != "":
    last_line = output_lines.pop()
    if last_line.endswith("\\\\"):
      last_line = re.sub(r"\\\\$", "", last_line)
    output_lines.append(last_line)
    output_lines.append("\\end{" + verse_type + "}")
  if ignore_chords == False and chord_line_buffer != "":
    output_lines.append(chord_line_buffer[prefix_length:])

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

  return formatted_lines

def main():
  with open("song_with_chords.json") as input_file:
    songs = json.load(input_file)
  prev_song = None
  for song in songs:
    try:
      is_in_done = os.path.exists("songs/done/" + slugify(song['title']) + ".tex")
      should_skip = input(f"Format '{song['title']}'  ({'y/N' if is_in_done else 'Y/n'}/a/r):")
      while should_skip != "" and should_skip[0] == 'r' and prev_song != None:
        song['latex'] = chords_2_latex(prev_song['chords'])
        user_check(prev_song)
        should_skip = input(f"Format '{song['title']}'  (Y/n/a/r):")
     
      if should_skip == "":
        if is_in_done:
          continue
        else:
          pass 
      elif should_skip.lower() == "y":
        pass
      elif should_skip[0].lower() == "n":
        continue
      elif should_skip[0] == 'a':
        return
        
      song['latex'] = chords_2_latex(song['chords'])
      user_check(song)

      prev_song = song
    except Exception as x:
      print("Encountered error formatting " + song['title'] + "\n" + str(x))
   



if __name__ == "__main__":
  main()
