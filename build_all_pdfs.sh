for x in `ls songs/`; do cp songs/$x songs/preview.tex && latexmk -pdf -pvc- -xelatex main.tex -outdir=output && mv output/main.pdf output/$x.pdf; done;
