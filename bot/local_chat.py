"""Interactive local chatbot. No Telegram token or external message delivery."""
from html import unescape
import argparse
import re
from bot.assistant import StudyAssistant
from bot.conversation import Conversation
from bot.local_llm import configured_llm, LocalModelError
from ingestion.bge_embeddings import Retriever


def plain(text):
    text = re.sub(r'<a href="([^"]+)">([^<]+)</a>',r'\2 (\1)',text)
    return unescape(re.sub(r'</?(?:b|i)>','',text))


class LazyRetriever:
    def __init__(self): self.instance=None
    def search(self,*args,**kwargs):
        if self.instance is None:
            print('\nSignal: Opening the study-resource search…')
            self.instance=Retriever()
        return self.instance.search(*args,**kwargs)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--warmup',action='store_true',help='Load both models before showing the menu')
    args=parser.parse_args()
    llm=configured_llm()
    if llm:
        print('Local answer model: Qwen3 4B Instruct (Ollama).' if llm.status() else
              'Local answer model is not ready. Start Ollama and run: ollama pull qwen3:4b-instruct\nSource search and course browsing remain available.')
    retriever=LazyRetriever()
    if args.warmup:
        print('Preparing the local models for your demo. The first load can take a little while.',flush=True)
        retriever.search('convolution',limit=1)
        if llm:
            try: llm.warmup()
            except LocalModelError: print('Ollama warm-up failed; source search remains available.')
        print('Preparation complete.',flush=True)
    conversation=Conversation(StudyAssistant(retriever,llm=llm))
    print(plain(conversation.welcome()))
    while True:
        try: text = input('\nYou: ').strip()
        except (EOFError,KeyboardInterrupt): break
        if text in ('/quit','/exit'): break
        if not text: continue
        try: print('\nSignal: '+plain(conversation.reply(text)))
        except Exception as exc: print('Local search could not finish: '+str(exc))


if __name__=='__main__': main()
