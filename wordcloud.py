import nltk
from nltk.corpus import gutenberg

# Download corpus if needed: nltk.download('gutenberg')
words = set(gutenberg.words('austen-sense.txt'))
isograms = [w for w in words if len(set(w.lower())) == len(w) and w.isalpha()]
print(isograms[:10])