"""Language-specific text handling for term matching: normalisation, stop-words, transliteration.

This is the only place in ``diga.terms`` that knows about particular languages; the spotting
and matching algorithms are language-agnostic.
"""

from __future__ import annotations

import re
import unicodedata

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
CYRILLIC_LANGUAGES = frozenset({"ru", "uk", "be", "bg", "sr", "mk", "kk"})


def normalize(text: str, language: str) -> str:
    """Lower-case, punctuation → spaces; ё→е for Russian; accents dropped for Latin scripts."""
    s = (text or "").lower()
    if language == "ru":
        s = s.replace("ё", "е")
    elif language not in CYRILLIC_LANGUAGES:
        s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return _NON_WORD.sub(" ", s).strip()


STOPWORDS: dict[str, frozenset[str]] = {
    "ru": frozenset(
        """и в не на я что он она оно они мы вы ты это как так его ее их но да у же вот только
        уже или ни быть был была было были есть нет от до по за из под над при о об для без
        более менее очень еще когда где куда откуда почему зачем потом тоже также чтобы если
        хотя причем притом просто прямо даже ведь разве пусть пока после перед между через
        сейчас теперь здесь там тут все весь вся всю свой своя свое свои мой моя мое мои твой
        ваш наш который которая которое которые кто чем том тем этом этим сам сама само сами
        себя меня тебя нас вас них него нее какой какая какое какие может можно нужно надо
        будет буду будем будете будут стал стала стало стали процесс процессы дела делать делаю
        делает делаем сделать сказать говорит говорю знаю знаете думаю хочу хотите можем начал
        начала конец начало время раз год день""".split()
    ),
    "en": frozenset(
        """a an the and or but if then so to of in on at by for with from as is are was were be
        been it its this that these those i you he she we they me him her us them my your our
        their not no do does did have has had can could will would should may might just also
        very there here what which who when where why how all any some""".split()
    ),
    "pt": frozenset(
        """o a os as um uma uns umas e ou mas se entao de do da dos das em no na nos nas por pelo
        pela para com sem que como e foi sao era ser estar esta este esta isto isso aquilo eu tu
        ele ela nos vos eles elas me te lhe se meu minha teu tua seu sua nao sim ja mais muito
        tambem aqui ali onde quando porque qual quem""".split()
    ),
}


def stopwords(*languages: str) -> frozenset[str]:
    return frozenset().union(*(STOPWORDS.get(lang, frozenset()) for lang in languages))


def dominant_script(text: str) -> str:
    """``"cyrillic"`` or ``"latin"`` — whichever alphabet most letters of ``text`` use."""
    cyrillic = sum("\u0400" <= c <= "\u04ff" for c in text)
    latin = sum(
        c.isalpha() and ("a" <= c.lower() <= "z" or "\u00c0" <= c <= "\u024f") for c in text
    )
    return "cyrillic" if cyrillic > latin else "latin"


_TO_CYRILLIC = {
    "shch": "щ",
    "sch": "щ",
    "yo": "ё",
    "zh": "ж",
    "kh": "х",
    "ts": "ц",
    "ch": "ч",
    "sh": "ш",
    "yu": "ю",
    "ya": "я",
    "a": "а",
    "b": "б",
    "v": "в",
    "g": "г",
    "d": "д",
    "e": "е",
    "z": "з",
    "i": "и",
    "j": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "f": "ф",
    "h": "х",
    "c": "к",
    "q": "к",
    "w": "в",
    "x": "кс",
    "y": "и",
}


def to_cyrillic(s: str) -> str:
    """Naive Latin → Cyrillic: roughly how a Russian speaker reads a Latin brand name."""
    out: list[str] = []
    low = s.lower()
    i = 0
    while i < len(low):
        for size in (4, 3, 2, 1):
            chunk = low[i : i + size]
            if chunk in _TO_CYRILLIC:
                out.append(_TO_CYRILLIC[chunk])
                i += size
                break
        else:
            out.append(low[i])
            i += 1
    return "".join(out)
