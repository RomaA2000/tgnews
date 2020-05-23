import nltk
import pickle
import json
import queue
from abc import abstractmethod
import sys
import threading
import warnings


warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
root_path = '.'
assets_path = root_path + '/assets'
out_path = root_path + '/out'
langs = ['ru', 'en']
categories = ["entertainment", "society", "technology", "sports", "science", "economy", "other"]


class TGExecutor:
    def __init__(self, max_workers):
        self.q = queue.SimpleQueue()
        self.threads = [threading.Thread(target=self._work) for i in range(max_workers)]

    def start(self):
        for t in self.threads:
            t.start()

    def join(self):
        for t in self.threads:
            t.join()

    def submit_data(self, data):
        self.q.put(data)

    def get_data(self, limit):
        data = [self.q.get()]
        for i in range(limit):
            try:
                data.append(self.q.get(False))
            except queue.Empty:
                break
        return data

    @abstractmethod
    def _work(self):
        pass


class TGServerExecutor(TGExecutor):
    def __init__(self, max_workers, lang):
        self.lang = lang
        super(TGServerExecutor, self).__init__(max_workers)
        self.start()

    def _work(self):
        net_sys = NetSystem(self.lang)
        while True:
            datalist = self.get_data(10)
            net_sys.process(datalist)


class NetSystem:
    def __init__(self, lang):
        self.lang = lang
        self.nets = TNetPack(lang)

    def process(self, datalist):
        names = [data[0] for data in datalist]
        texts = [self.nets.stemmer.stem(data[1]) for data in datalist]
        news_test = self.nets.news_net.predict(texts)

        names = [names[i] for i in range(len(texts)) if news_test[i]]
        texts = [texts[i] for i in range(len(texts)) if news_test[i]]

        try:
            categories_test = self.nets.class_net.predict(texts)
        except Exception:
            print(self.lang + ':: Error: Categorization failed')
            return

        for i in range(len(texts)):
            cat = categories[int(categories_test[i])]
            dump_info({"file_name": names[i], "lang": self.lang, "category": cat})


class TNetPack:
    def __init__(self, lang):
        self.stemmer = TStemmer(lang)
        self.news_net = TNet('news', lang) if lang == 'ru' else ENNewsNet()
        self.class_net = TNet('categories', lang)


class SimNet:
    def __init__(self, net_type, lang):
        self.stemmer = TStemmer(lang)
        if net_type == 'news' and lang == 'en':
            self.net = ENNewsNet()
        else:
            self.net = TNet(net_type, lang)

    def predict(self, texts):
        texts = [self.stemmer.stem(text) for text in texts]
        return self.net.predict(texts)


class TStemmer:
    def __init__(self, lang):
        self.stemmer = get_stemmer(lang)

    def stem(self, text):
        return ' '.join(map(lambda w: self.stemmer.stem(w), text.split()))


class TNet:
    def __init__(self, net_type, lang):
        self.model = get_model(lang, net_type)
        self.vectorizer = get_vectorizer(lang, net_type)

    def predict(self, stemmed_texts):
        x_tfidf = self.vectorizer.transform(stemmed_texts)
        return self.model.predict(x_tfidf)


class ENNewsNet(TNet):
    def __init__(self):
        super(ENNewsNet, self).__init__('news', 'en')

    def predict(self, stemmed_texts):
        x_tfidf = self.vectorizer.transform(stemmed_texts)
        ans = (0.45 < self.model.predict_proba(x_tfidf)[:, 1:])
        return flatten(ans)


def flatten(lst):
    return [item for sublist in lst for item in sublist]


def form_path(lang, category, name):
    return out_path + '/' + lang + '/' + category + '/' + name


def dump_info(js):
    path = form_path(js['lang'], js['category'], js['file_name'])
    with open(path, 'w') as file:
        file.write(json.dumps(js))


def get_stemmer(lang):
    if lang == 'ru':
        return nltk.stem.snowball.RussianStemmer()
    elif lang == 'en':
        return nltk.stem.snowball.EnglishStemmer()


def get_vectorizer(lang, net):
    return load(assets_path + '/' + net + '/' + lang + '/vectorizer.pickle')


def get_model(lang, net):
    return load(assets_path + '/' + net + '/' + lang + '/model.pickle')


def load(path):
    try:
        with open(path, 'rb') as file:
            return pickle.load(file)
    except Exception:
        print("ERROR: Failed to load: " + path)


def tokenize(s):
    return s.split()


class SimExecutor(TGExecutor):
    def __init__(self, max_workers, net_type, lang):
        self.lang = lang
        self.net_type = net_type
        self.result = queue.SimpleQueue()
        super(SimExecutor, self).__init__(max_workers)

    def _work(self):
        net = SimNet(self.net_type, self.lang)
        res = []
        while not self.q.empty():
            texts = []
            files = self.get_data(10)
            for art in files:
                with open(art, 'r') as art_file:
                    texts.append(art_file.read())

            rs = net.predict(texts)
            for i in range(len(texts)):
                res.append([files[i].split('/')[-1], rs[i]])

        for r in res:
            self.result.put(r)


if __name__ == '__main__':
    net_type = sys.argv[1]
    path = sys.argv[2]

    executors = {'ru': SimExecutor(8, net_type, 'ru'), 'en': SimExecutor(8, net_type, 'en')}

    with open(path, 'r') as file:
        js = json.load(file)

    for entry in js:
        lang = entry['lang_code']
        for article in entry['articles']:
            executors[lang].submit_data(article)

    for ex in executors:
        executors[ex].start()

    for ex in executors:
        executors[ex].join()

    if net_type == 'news':
        list_art = []
        for ex in executors:
            q = executors[ex].result
            while not q.empty():
                item = q.get()
                if item[1]:
                    list_art.append(item[0])

        result = {'articles': list_art}
    else:
        result = []
        mp = {}
        for cat in categories:
            mp[cat] = []

        for ex in executors:
            q = executors[ex].result
            while not q.empty():
                item = q.get()
                mp[categories[item[1]]].append(item[0])

        for cat in categories:
            if len(mp[cat]) > 0:
                result.append({"category": cat, "articles": mp[cat]})

    print(json.dumps(result, indent=2))
