.PHONY: all watch clean distclean

MAIN := main
LATEXMK := latexmk
LATEXMK_FLAGS :=

all:
	$(LATEXMK) $(LATEXMK_FLAGS) $(MAIN).tex

watch:
	$(LATEXMK) $(LATEXMK_FLAGS) -pvc $(MAIN).tex

clean:
	$(LATEXMK) -c

distclean:
	$(LATEXMK) -C
	rm -f $(MAIN).pdf
