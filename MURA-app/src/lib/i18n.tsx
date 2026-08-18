"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { UiLanguage } from "@/lib/language";

export type Locale = UiLanguage;

const ui = {
  ru: {
    begin: "Начать",
    tagline: "Голос вашей семьи.\nНавсегда.",
    memoryLives: "Каждое воспоминание заслуживает жить.",
    goodNight: "Доброй ночи",
    goodMorning: "Доброе утро",
    goodAfternoon: "Добрый день",
    goodEvening: "Добрый вечер",
    todaysMemories: "Воспоминания сегодня",
    recordMemory: "Записать воспоминание",
    pressAndSpeak: "Нажмите и говорите",
    familyTree: "Семейное древо",
    // One object, one word. The archive used to call the same thing
    // «рассказ» in the tab bar, «воспоминание» on its own page and «запись»
    // on Home — three names for one object, so the user had to work out that
    // they were the same. «Запись» and «рассказ» stay in the domain model
    // (Recording, Story) and in the code, but not in the interface.
    recentRecordings: "Недавние воспоминания",
    people: "человек",
    memories: "воспоминаний",
    new: "Новое",
    newMemory: "Новое воспоминание",
    startRecording: "Начать запись",
    rememberPrompt: "Расскажите так,\nкак вы это помните.",
    // «Просто говорите» said what the button below it already says, on a
    // screen whose whole job is to have as little on it as possible.
    rememberHint: "Здесь нельзя вспоминать неправильно.",
    listening: "Слушаю",
    liveTextUnavailable: "Аудио записывается. Русско-казахский текст появится после обработки.",
    speechRecognitionError: "Не удалось распознать речь. Аудиозапись продолжается.",
    restart: "Сначала",
    resume: "Продолжить",
    pause: "Пауза",
    finish: "Готово",
    uploading: "Отправляем запись…",
    loadingSpeechModel: "Загружаем модель распознавания: {progress}%",
    improvingTranscript: "Точно распознаём казахскую речь…",
    microphoneError: "Не удалось открыть микрофон. Разрешите доступ и попробуйте снова.",
    uploadError: "Не удалось обработать запись. Попробуйте ещё раз.",
    noSpeechError: "Речь не распознана. Скажите несколько слов и попробуйте снова.",
    audioMemoryTitle: "Новая аудиозапись",
    transcriptUnavailable: "Текст не распознан, но аудиозапись сохранена.",
    noSavedMemories: "Здесь появятся ваши новые записи.",
    aiSummary: "Кратко",
    transcript: "Расшифровка",
    memoryNotFound: "Запись не найдена в этом браузере.",
    archiveOwnerSummary: "Здесь сохраняются ваши настоящие аудиозаписи и воспоминания.",
    processingListen: "Слушаем ещё раз…",
    processingPeople: "Находим людей…",
    processingPlace: "Добавляем в историю семьи…",
    processingSafe: "Ваши слова в безопасности. Нужно немного времени.",
    processingFailureTitle: "Запись сохранена",
    processingFailed: "GigaAM сейчас недоступен. Перезапустите Kaggle worker и повторите обработку.",
    retrySavedRecording: "Повторить эту запись",
    retryNeedsWorker: "Сначала перезапустите Kaggle worker.",
    asrUnavailableTitle: "Распознавание речи временно недоступно",
    asrUnavailableBody: "Запись сохранена. Можно подождать или продолжить без распознавания.",
    asrRetryIn: "Повторим через",
    asrRetryNow: "Повторить сейчас",
    asrWaiting: "Ждём распознавание речи…",
    openTranscriptFallback: "Ввести текст вручную",
    openDemoExample: "Открыть демонстрационный пример",
    demoReplayBadge: "Демо-повтор",
    tryAgain: "Попробовать ещё раз",
    seconds: "с",
    personNotFound: "Такого человека нет в вашем архиве.",
    personLoading: "Открываем профиль…",
    personStories: "Воспоминания",
    personNoStories: "Пока нет рассказов об этом человеке.",
    personConnections: "Связи в семье",
    personPlaces: "Места",
    personKnownAs: "Также упоминается как",
    storiesTitle: "Воспоминания",
    storiesLoading: "Открываем воспоминания…",
    storiesEmptyTitle: "Здесь появятся ваши рассказы",
    storiesEmptyBody: "Запишите первый рассказ — MURA расшифрует его и добавит в семейный архив.",
    storyNotFound: "Это воспоминание не найдено в вашем архиве.",
    storyLoading: "Открываем воспоминание…",
    storyUntitled: "Без названия",
    // Relative dates only where they genuinely read better than a date.
    storyToday: "сегодня",
    storyYesterday: "вчера",
    storyThisWeek: "на этой неделе",
    // «и ещё 2» after the first three names on a memory card.
    storyMorePeople: "и ещё {count}",
    // Home: the archive found two versions of the same fact and kept both.
    // Worded as something the family said, not as a data-integrity problem.
    homeOpenConflicts: "В рассказах есть разные версии",
    conflictCountOne: "расхождение",
    conflictCountFew: "расхождения",
    conflictCountMany: "расхождений",
    // «Показано 30 из 128» — the list was silently cut at 30 before.
    storiesShownOf: "Показано {shown} из {total}",
    storiesLoadMore: "Показать ещё",
    searchOpen: "Поиск по архиву",
    searchTitle: "Поиск по архиву",
    searchPlaceholder: "Имя или слово из рассказа",
    searchClose: "Закрыть поиск",
    searchAll: "Всё",
    searchPerson: "Человек",
    searchNothing: "Ничего не нашлось",
    searchLoading: "Открываем архив…",
    searchResultCount: "Найдено: {count}",
    // The reach of the search, said plainly. Core has no search endpoint, so
    // this filters the page it could load — and an empty result must not read
    // as «в вашем архиве этого нет».
    searchPartial: "Поиск идёт по {loaded} воспоминаниям из {total}. Остальные пока не участвуют.",
    storiesLoadingMore: "Загружаем…",
    // Not «Рассказал(а)»: a bracketed suffix is a developer working around
    // grammatical gender in front of the reader, in the middle of what is
    // meant to be a memoir. «Со слов» is genderless, natural, and archival —
    // and, like the Kazakh «{name} айтқан», it asserts nothing about the
    // speaker that the archive did not record.
    storyToldBy: "Со слов {name}",
    storyAudioUnavailable: "Аудиозапись недоступна.",
    storySourceTitle: "Источник",
    storySourceLine: "Из записи от {date}",
    reviewTitle: "Нужно уточнить",
    reviewLoading: "Проверяем архив…",
    reviewEmptyTitle: "Всё ясно",
    reviewEmptyBody: "Сейчас в архиве нет вопросов, требующих уточнения.",
    reviewQuestion: "Вопрос",
    reviewConflict: "Разные версии",
    reviewCountOne: "вопрос",
    reviewCountFew: "вопроса",
    reviewCountMany: "вопросов",
    relFather: "Отец",
    relMother: "Родитель",
    // Gender-safe, like «Со слов {name}» elsewhere. These label a specific
    // person whose gender the archive never recorded, so «Супруг(а)» was the
    // same defect the product already rejected in «Рассказал(а)» — and
    // «Брат/сестра», «Дедушка/бабушка», «Внук/внучка» were the same defect
    // wearing a slash. A slash is a shorthand for "we are guessing"; spelling
    // the alternative out says plainly that the archive knows the relation
    // but not the person's gender.
    // The centre card names its own frame, because «бабушка» alone does not
    // say whose grandmother. `relation_to_speaker` arrives lowercase from the
    // archive, so the sentence is built around it rather than capitalised.
    relToNarrator: "{relation} рассказчика",
    relParent: "Родитель",
    relChild: "Ребёнок",
    relSpouse: "В браке",
    relSibling: "Брат или сестра",
    relGrandparent: "Дедушка или бабушка",
    relGrandchild: "Внук или внучка",
    treeEmptyTitle: "Семейное древо начнёт расти после первых рассказов",
    treeEmptyBody: "Когда вы запишете рассказ, MURA найдёт в нём людей и связи и покажет их здесь.",
    treeLoading: "Открываем семейное древо…",
    // Not «не связаны»: this strip now lists everyone the canvas cannot place
    // around the person in the centre, and some of them are related — just not
    // to this person. Saying they are unconnected would be a family fact the
    // archive never asserted.
    treeOtherPeople: "Не показаны рядом с этим человеком",
    treeCanvasLabel: "Семейное древо, интерактивная схема",
    treeKeyboardHelp:
      "Стрелки — перемещение, плюс и минус — масштаб, ноль — показать целиком. Tab — переход между людьми, Enter — открыть.",
    treeZoomIn: "Приблизить",
    treeZoomOut: "Отдалить",
    treeFit: "Показать целиком",
    closePanel: "Закрыть",
    // Islands are separate because no recording has connected them yet — not
    // because the connection is doubted.
    treeIslandLabel: "Пока отдельная ветвь",
    // Connected, just not drawable around this particular person.
    treeFurtherLabel: "Дальше по этой ветви",
    treeIslandsHint:
      "Эти люди пока не связаны с остальными — в записях об этом ещё не рассказали.",
    archiveError: "Не удалось загрузить семейный архив.",
    archiveRetry: "Попробовать снова",
    archiveForbidden: "У вас нет доступа к этому разделу.",
    settingsLanguage: "Язык интерфейса",
    settingsLanguageHint: "Язык записи определяется автоматически при обработке.",
    settingsAccount: "Аккаунт",
    accountSignedIn: "Вы вошли в MURA",
    settingsFamily: "Семья",
    homePeopleOne: "человек",
    homePeopleFew: "человека",
    homePeopleMany: "человек",
    homeStoriesOne: "рассказ",
    homeStoriesFew: "рассказа",
    homeStoriesMany: "рассказов",
    homeOpenTree: "Семейное древо",
    homeOpenStories: "Все воспоминания",
    homeOpenReview: "Нужно уточнить",
    homeEmptyTitle: "Здесь пока пусто",
    homeEmptyBody: "Запишите первый рассказ — он появится здесь и войдёт в семейный архив.",
    askCardTitle: "Спросить о семье",
    askCardBody: "Задайте вопрос о родных и событиях.",
    exploreFamily: "Семейное древо",
    navHome: "Главная",
    navFamily: "Семья",
    navRecord: "Записать",
    navAsk: "Спросить",
    navStories: "Воспоминания",
    navSettings: "Настройки",
    navPrimary: "Основное",
    skipToContent: "Перейти к содержимому",
    yourArchive: "Ваш семейный архив",
    noFamilyYet: "Семья ещё не создана",
    signedOutArchive: "Демо-режим",
    demoBadge: "Пример",
    demoTreeTitle: "Пример семейного древа",
    demoTreeNotice: "Это демонстрационная семья, а не ваш архив.",
    demoTreeNoticeSignedIn:
      "Это демонстрационная семья. Ваш семейный архив здесь пока не показывается.",
    demoStoryNotice: "Это демонстрационное воспоминание, а не запись вашей семьи.",
    demoPersonNotice: "Это человек из демонстрационной семьи, а не из вашего архива.",
    demoAskNotice: "Это демонстрация. Ответы заранее записаны и не основаны на вашем архиве.",
    demoAskAnswerBadge: "Демонстрационный ответ",
    demoAudioUnavailable: "Аудио недоступно: это демонстрационный пример.",
    yourFamily: "Ваша семья",
    familyOf: "Семья: {name}",
    newMemoryPlaced: "Новое воспоминание добавлено",
    treeHint: "Перетаскивайте · масштабируйте · нажмите на человека",
    centerTree: "Центрировать древо",
    noMemoriesYet: "Пока нет воспоминаний",
    oneMemory: "1 воспоминание",
    memoriesCount: "{count} воспоминаний",
    oneMemoryRecorded: "Записано 1 воспоминание",
    memoriesRecorded: "Записано воспоминаний: {count}",
    openProfile: "Открыть профиль",
    centerHere: "Поставить в центр",
    hideParents: "Скрыть родителей: {name}",
    showParents: "Показать родителей: {name}",
    hideChildren: "Скрыть детей: {name}",
    showChildren: "Показать детей: {name}",
    memory: "Воспоминание",
    // Was «Рассказала», which asserted the speaker is a woman. The archive
    // records who spoke, never their gender.
    toldBy: "Со слов {name}",
    inThisMemory: "В этом воспоминании",
    listen: "Слушать",
    play: "Воспроизвести",
    pauseAudio: "Пауза",
    born: "Год рождения: {year}",
    memoriesTold: "Воспоминания, рассказанные {name}",
    noMention: "Пока нет воспоминаний о {name}.",
    nextMention: "Когда в следующий раз будете говорить о {name}, нажмите запись.",
    recordAMemory: "Записать воспоминание",
    relationOf: "{relation} для {name}",
    goBack: "Назад",
    father: "Отец",
    mother: "Мать",
    husband: "Муж",
    wife: "Жена",
    brother: "Брат",
    sister: "Сестра",
    son: "Сын",
    daughter: "Дочь",
    grandfather: "Дедушка",
    grandmother: "Бабушка",
    grandson: "Внук",
    granddaughter: "Внучка",
    settings: "Настройки",
    openSettings: "Открыть настройки",
    askMemory: "Спросить о семье",
    askTitle: "О чём вы хотите\nвспомнить?",
    askHint: "Например: «Что делал Мустафа?»",
    askSpeakNow: "Спрашивайте",
    askFinish: "Готово",
    askThinking: "Думаю…",
    askSearching: "Нашла. Сейчас расскажу…",
    askNotFound: "Пока не нахожу такого воспоминания.\nПопробуйте спросить о Мустафе.",
    askAgain: "Спросить снова",
    memoryFound: "Воспоминание найдено",
    mustafaTitle: "Мустафа на alem techfest 2026",
    mustafaEra: "26 июля 2026 · Астана",
    mustafaSummary:
      "Команда NEURA #26946 на чемпионате FIRST в Центральной Азии. Мустафа с командой на сцене.",
    mustafaPhotoTeam: "Команда NEURA на сцене alem techfest 2026",
    mustafaPhotoPortrait: "Мустафа с командой на площадке чемпионата",
    analysisPending: "Пересказ появится, когда анализ завершится.",
    analysisFailed: "Анализ не завершился. Аудиозапись и расшифровка сохранены.",
    retryAnalysis: "Повторить анализ",
    eventsAndPlaces: "События и места",
    addedFromMemory: "Добавлен в семейное древо из этого воспоминания",
    openInTree: "Открыть в семейном дереве",
    needsReviewNote: "Некоторые детали требуют уточнения.",
    signIn: "Войти",
    signUp: "Создать аккаунт",
    signOut: "Выйти",
    account: "Аккаунт",
    coreUnavailable: "Не удалось подключиться к MURA.",
    coreUnavailableHint: "Проверьте, запущен ли сервис, и попробуйте обновить страницу.",
    familyRequiredToRecord: "Сначала выберите или создайте семью.",
    recordingUnsupported: "Этот браузер не поддерживает запись звука.",
    microphoneDenied: "Разрешите доступ к микрофону в настройках браузера.",
    microphoneMissing: "Микрофон не найден. Подключите его и обновите страницу.",
    processingUnconfigured: "Анализ речи пока не настроен на сервере.",
    processingDelayedNotice: "Сервис анализа сейчас недоступен — запись сохранится и будет обработана позже.",
    signInToSave: "Войдите, чтобы записывать воспоминания",
    signInToSaveHint: "Войдите, чтобы открыть семейный архив и записывать воспоминания.",
    signInToSaveHintSettings: "Войдите, чтобы управлять семейным архивом и участниками.",
    sessionLoading: "Открываем архив…",
    signInRequired: "Войдите, чтобы открыть семейный архив.",
    signInProviderPending: "Вход ещё не подключён. Семейный архив откроется, когда появится вход.",
    sessionExpired: "Сессия недействительна. Войдите снова.",
    permissionDenied: "У вашей роли нет прав на это действие.",
    familyUnavailable: "Эта семья больше не доступна.",
    familyLoadFailed: "Не удалось загрузить список семей.",
    noFamilyTitle: "Создайте свою семью",
    noFamilyHint: "Все записи и воспоминания будут храниться в ней.",
    familyNameLabel: "Название семьи",
    familyNamePlaceholder: "Например: Семья Айсұлу",
    createFamily: "Создать семью",
    creatingFamily: "Создаём…",
    createFamilyFailed: "Не удалось создать семью. Попробуйте ещё раз.",
    switchFamily: "Сменить семью",
    currentFamily: "Текущая семья",
    roleOwner: "Владелец",
    roleEditor: "Редактор",
    roleViewer: "Наблюдатель",
    recordingNotAllowed: "У вашей роли нет прав на запись в этой семье.",
  },
  kk: {
    begin: "Бастау",
    tagline: "Отбасыңыздың дауысы.\nМәңгілікке.",
    memoryLives: "Әрбір естелік өмір сүруге лайық.",
    goodNight: "Қайырлы түн",
    goodMorning: "Қайырлы таң",
    goodAfternoon: "Қайырлы күн",
    goodEvening: "Қайырлы кеш",
    todaysMemories: "Бүгінгі естеліктер",
    recordMemory: "Естелік жазу",
    pressAndSpeak: "Басыңыз да, сөйлей беріңіз",
    familyTree: "Отбасы шежіресі",
    recentRecordings: "Соңғы естеліктер",
    people: "адам",
    memories: "естелік",
    new: "Жаңа",
    newMemory: "Жаңа естелік",
    startRecording: "Жазуды бастау",
    rememberPrompt: "Қалай есіңізде болса,\nсолай айтыңыз.",
    rememberHint: "Еске алудың қате жолы жоқ.",
    listening: "Тыңдап тұрмын",
    liveTextUnavailable: "Аудио жазылып жатыр. Қазақша-орысша мәтін өңдеуден кейін пайда болады.",
    speechRecognitionError: "Сөйлеуді тану мүмкін болмады. Аудио жазу жалғасуда.",
    restart: "Қайта бастау",
    resume: "Жалғастыру",
    pause: "Кідірту",
    finish: "Аяқтау",
    uploading: "Жазба жіберіліп жатыр…",
    loadingSpeechModel: "Сөйлеуді тану моделі жүктелуде: {progress}%",
    improvingTranscript: "Қазақша сөздерді мұқият танып жатырмыз…",
    microphoneError: "Микрофон ашылмады. Рұқсат беріп, қайта көріңіз.",
    uploadError: "Жазбаны өңдеу мүмкін болмады. Қайта көріңіз.",
    noSpeechError: "Сөйлеу танылмады. Бірнеше сөз айтып, қайта көріңіз.",
    audioMemoryTitle: "Жаңа аудиожазба",
    transcriptUnavailable: "Мәтін танылмады, бірақ аудиожазба сақталды.",
    noSavedMemories: "Жаңа жазбаларыңыз осында пайда болады.",
    aiSummary: "Қысқаша",
    transcript: "Мәтін",
    memoryNotFound: "Бұл браузерде жазба табылмады.",
    archiveOwnerSummary: "Мұнда сіздің нақты аудиожазбаларыңыз бен естеліктеріңіз сақталады.",
    processingListen: "Тағы бір рет тыңдап жатырмыз…",
    processingPeople: "Адамдарды тауып жатырмыз…",
    processingPlace: "Отбасы тарихына қосып жатырмыз…",
    processingSafe: "Сөздеріңіз қауіпсіз. Аз ғана уақыт қажет.",
    processingFailureTitle: "Жазба сақталды",
    processingFailed: "GigaAM қазір қолжетімсіз. Kaggle worker-ді қайта қосып, өңдеуді қайталаңыз.",
    retrySavedRecording: "Осы жазбаны қайталау",
    retryNeedsWorker: "Алдымен Kaggle worker-ді қайта қосыңыз.",
    asrUnavailableTitle: "Сөзді тану уақытша қолжетімсіз",
    asrUnavailableBody: "Жазба сақталды. Күтуге не тануcыз жалғастыруға болады.",
    asrRetryIn: "Қайталаймыз",
    asrRetryNow: "Қазір қайталау",
    asrWaiting: "Сөзді тануды күтудеміз…",
    openTranscriptFallback: "Мәтінді қолмен енгізу",
    openDemoExample: "Демонстрациялық мысалды ашу",
    demoReplayBadge: "Демо-қайталау",
    tryAgain: "Қайта көру",
    seconds: "с",
    personNotFound: "Мұндай адам сіздің мұрағатыңызда жоқ.",
    personLoading: "Профиль ашылып жатыр…",
    personStories: "Естеліктер",
    personNoStories: "Бұл адам туралы әзірге әңгіме жоқ.",
    personConnections: "Отбасылық байланыстар",
    personPlaces: "Орындар",
    personKnownAs: "Сондай-ақ аталады",
    storiesTitle: "Естеліктер",
    storiesLoading: "Естеліктер ашылып жатыр…",
    storiesEmptyTitle: "Мұнда сіздің әңгімелеріңіз пайда болады",
    storiesEmptyBody: "Алғашқы әңгімені жазыңыз — MURA оны мәтінге айналдырып, мұрағатқа қосады.",
    storyNotFound: "Бұл естелік мұрағатыңыздан табылмады.",
    storyLoading: "Естелік ашылып жатыр…",
    storyUntitled: "Атауы жоқ",
    storyToday: "бүгін",
    storyYesterday: "кеше",
    storyThisWeek: "осы аптада",
    storyMorePeople: "тағы {count}",
    homeOpenConflicts: "Әңгімелерде әртүрлі нұсқалар бар",
    conflictCountOne: "алшақтық",
    conflictCountFew: "алшақтық",
    conflictCountMany: "алшақтық",
    storiesShownOf: "{total} ішінен {shown} көрсетілді",
    storiesLoadMore: "Тағы көрсету",
    searchOpen: "Мұрағаттан іздеу",
    searchTitle: "Мұрағаттан іздеу",
    searchPlaceholder: "Есім немесе әңгімеден сөз",
    searchClose: "Іздеуді жабу",
    searchAll: "Барлығы",
    searchPerson: "Адам",
    searchNothing: "Ештеңе табылмады",
    searchLoading: "Мұрағат ашылуда…",
    searchResultCount: "Табылды: {count}",
    searchPartial: "Іздеу {total} естеліктің {loaded} бойынша жүреді. Қалғаны әзірге қамтылмаған.",
    storiesLoadingMore: "Жүктелуде…",
    storyToldBy: "{name} айтқан",
    storyAudioUnavailable: "Аудиожазба қолжетімсіз.",
    storySourceTitle: "Дереккөз",
    storySourceLine: "{date} жазбасынан",
    reviewTitle: "Нақтылау қажет",
    reviewLoading: "Мұрағат тексерілуде…",
    reviewEmptyTitle: "Бәрі анық",
    reviewEmptyBody: "Қазір мұрағатта нақтылауды қажет ететін сұрақтар жоқ.",
    reviewQuestion: "Сұрақ",
    reviewConflict: "Әртүрлі нұсқалар",
    reviewCountOne: "сұрақ",
    reviewCountFew: "сұрақ",
    reviewCountMany: "сұрақ",
    relFather: "Әкесі",
    relMother: "Ата-анасы",
    relToNarrator: "Әңгімешінің {relation}",
    relParent: "Ата-анасы",
    relChild: "Баласы",
    relSpouse: "Жұбайы",
    relSibling: "Бауыры",
    relGrandparent: "Атасы не әжесі",
    relGrandchild: "Немересі",
    treeEmptyTitle: "Шежіре алғашқы әңгімелерден кейін өсе бастайды",
    treeEmptyBody: "Әңгіме жазғаныңызда MURA ондағы адамдар мен байланыстарды тауып, осында көрсетеді.",
    treeLoading: "Шежіре ашылып жатыр…",
    treeOtherPeople: "Бұл адамның қасында көрсетілмеген",
    treeCanvasLabel: "Отбасы шежіресі, интерактивті сызба",
    treeKeyboardHelp:
      "Бағыттауыш пернелер — жылжыту, плюс пен минус — масштаб, нөл — толық көрсету. Tab — адамдар арасында өту, Enter — ашу.",
    treeZoomIn: "Жақындату",
    treeZoomOut: "Алыстату",
    treeFit: "Толық көрсету",
    closePanel: "Жабу",
    treeIslandLabel: "Әзірге бөлек тармақ",
    treeFurtherLabel: "Осы тармақтың әрі қарайы",
    treeIslandsHint:
      "Бұл адамдар әзірге басқалармен байланыспаған — жазбаларда ол туралы әлі айтылмаған.",
    archiveError: "Отбасылық мұрағатты жүктеу мүмкін болмады.",
    archiveRetry: "Қайта көру",
    archiveForbidden: "Бұл бөлімге қолжетімділік жоқ.",
    settingsLanguage: "Интерфейс тілі",
    settingsLanguageHint: "Жазба тілі өңдеу кезінде автоматты түрде анықталады.",
    accountSignedIn: "Сіз MURA-ға кірдіңіз",
    settingsAccount: "Аккаунт",
    settingsFamily: "Отбасы",
    homePeopleOne: "адам",
    homePeopleFew: "адам",
    homePeopleMany: "адам",
    homeStoriesOne: "әңгіме",
    homeStoriesFew: "әңгіме",
    homeStoriesMany: "әңгіме",
    homeOpenTree: "Отбасы шежіресі",
    homeOpenStories: "Барлық естеліктер",
    homeOpenReview: "Нақтылау қажет",
    homeEmptyTitle: "Мұнда әзірге бос",
    homeEmptyBody: "Алғашқы әңгімені жазыңыз — ол осында шығып, отбасылық мұрағатқа қосылады.",
    askCardTitle: "Отбасы туралы сұрау",
    askCardBody: "Туыстар мен оқиғалар туралы сұрақ қойыңыз.",
    exploreFamily: "Отбасы шежіресі",
    navHome: "Басты",
    navFamily: "Отбасы",
    navRecord: "Жазу",
    navAsk: "Сұрау",
    navStories: "Естеліктер",
    navSettings: "Параметрлер",
    navPrimary: "Негізгі",
    skipToContent: "Мазмұнға өту",
    yourArchive: "Сіздің отбасылық мұрағатыңыз",
    noFamilyYet: "Отбасы әзірге құрылмаған",
    signedOutArchive: "Демо-режим",
    demoBadge: "Мысал",
    demoTreeTitle: "Демонстрациялық шежіре",
    demoTreeNotice: "Бұл — демонстрациялық отбасы, сіздің архивіңіз емес.",
    demoTreeNoticeSignedIn:
      "Бұл — демонстрациялық отбасы. Сіздің отбасылық архивіңіз мұнда әзірге көрсетілмейді.",
    demoStoryNotice: "Бұл — демонстрациялық естелік, сіздің отбасыңыздың жазбасы емес.",
    demoPersonNotice: "Бұл — демонстрациялық отбасының адамы, сіздің архивіңізден емес.",
    demoAskNotice:
      "Бұл — демонстрация. Жауаптар алдын ала жазылған және сіздің архивіңізге негізделмеген.",
    demoAskAnswerBadge: "Демонстрациялық жауап",
    demoAudioUnavailable: "Аудио қолжетімсіз: бұл — демонстрациялық мысал.",
    yourFamily: "Сіздің отбасыңыз",
    familyOf: "{name} отбасы",
    newMemoryPlaced: "Жаңа естелік қосылды",
    treeHint: "Жылжытыңыз · масштабтаңыз · адамды түртіңіз",
    centerTree: "Шежірені ортаға келтіру",
    noMemoriesYet: "Әзірге естелік жоқ",
    oneMemory: "1 естелік",
    memoriesCount: "{count} естелік",
    oneMemoryRecorded: "1 естелік жазылған",
    memoriesRecorded: "{count} естелік жазылған",
    openProfile: "Профильді ашу",
    centerHere: "Ортаға қою",
    hideParents: "{name} ата-анасын жасыру",
    showParents: "{name} ата-анасын көрсету",
    hideChildren: "{name} балаларын жасыру",
    showChildren: "{name} балаларын көрсету",
    memory: "Естелік",
    toldBy: "Айтқан: {name}",
    inThisMemory: "Бұл естелікте",
    listen: "Тыңдау",
    play: "Ойнату",
    pauseAudio: "Кідірту",
    born: "Туған жылы: {year}",
    memoriesTold: "{name} айтқан естеліктер",
    noMention: "{name} туралы әзірге естелік жоқ.",
    nextMention: "Келесіде {name} туралы айтқанда, жазу түймесін басыңыз.",
    recordAMemory: "Естелік жазу",
    relationOf: "{name} үшін: {relation}",
    goBack: "Артқа",
    father: "Әкесі",
    mother: "Анасы",
    husband: "Күйеуі",
    wife: "Жұбайы",
    brother: "Ағасы/інісі",
    sister: "Әпкесі/сіңлісі",
    son: "Ұлы",
    daughter: "Қызы",
    grandfather: "Атасы",
    grandmother: "Әжесі",
    grandson: "Немересі",
    granddaughter: "Немересі",
    settings: "Параметрлер",
    openSettings: "Параметрлерді ашу",
    askMemory: "Отбасы туралы сұрау",
    askTitle: "Нені еске\nтүсіргіңіз келеді?",
    askHint: "Мысалы: «Мұстафа не істеді?»",
    askSpeakNow: "Сұрай беріңіз",
    askFinish: "Дайын",
    askThinking: "Ойланып жатырмын…",
    askSearching: "Таптым. Қазір айтамын…",
    askNotFound: "Әзірге мұндай естелік табылмады.\nМұстафа туралы сұрап көріңіз.",
    askAgain: "Қайта сұрау",
    memoryFound: "Естелік табылды",
    mustafaTitle: "alem techfest 2026-дағы Мұстафа",
    mustafaEra: "2026 жылғы 26 шілде · Астана",
    mustafaSummary:
      "NEURA #26946 командасы Орталық Азиядағы FIRST чемпионатында. Мұстафа командасымен сахнада.",
    mustafaPhotoTeam: "alem techfest 2026 сахнасындағы NEURA командасы",
    mustafaPhotoPortrait: "Мұстафа чемпионат алаңында командасымен",
    analysisPending: "Талдау аяқталған соң қысқаша мазмұн пайда болады.",
    analysisFailed: "Талдау аяқталмады. Аудиожазба мен мәтін сақталды.",
    retryAnalysis: "Талдауды қайталау",
    eventsAndPlaces: "Оқиғалар мен орындар",
    addedFromMemory: "Осы естеліктен отбасы шежіресіне қосылды",
    openInTree: "Отбасы шежіресінен ашу",
    needsReviewNote: "Кейбір мәліметтерді нақтылау қажет.",
    signIn: "Кіру",
    signUp: "Аккаунт құру",
    signOut: "Шығу",
    account: "Аккаунт",
    coreUnavailable: "MURA-ға қосылу мүмкін болмады.",
    coreUnavailableHint: "Сервис қосулы ма, тексеріп, бетті жаңартып көріңіз.",
    familyRequiredToRecord: "Алдымен отбасын таңдаңыз немесе құрыңыз.",
    recordingUnsupported: "Бұл браузер дыбыс жазуды қолдамайды.",
    microphoneDenied: "Браузер параметрлерінде микрофонға рұқсат беріңіз.",
    microphoneMissing: "Микрофон табылмады. Қосып, бетті жаңартыңыз.",
    processingUnconfigured: "Сөзді талдау сервері әзірге бапталмаған.",
    processingDelayedNotice: "Талдау қызметі қазір қолжетімсіз — жазба сақталып, кейін өңделеді.",
    signInToSave: "Естеліктерді жазу үшін кіріңіз",
    signInToSaveHint: "Отбасылық мұрағатты ашу және естелік жазу үшін кіріңіз.",
    signInToSaveHintSettings: "Отбасылық мұрағат пен қатысушыларды басқару үшін кіріңіз.",
    sessionLoading: "Мұрағатты ашып жатырмыз…",
    signInRequired: "Отбасы мұрағатын ашу үшін кіріңіз.",
    signInProviderPending: "Кіру әзірге қосылмаған. Кіру пайда болғанда мұрағат ашылады.",
    sessionExpired: "Сессия жарамсыз. Қайта кіріңіз.",
    permissionDenied: "Сіздің рөліңізде бұл әрекетке рұқсат жоқ.",
    familyUnavailable: "Бұл отбасы қолжетімді емес.",
    familyLoadFailed: "Отбасылар тізімін жүктеу мүмкін болмады.",
    noFamilyTitle: "Отбасыңызды құрыңыз",
    noFamilyHint: "Барлық жазбалар мен естеліктер сонда сақталады.",
    familyNameLabel: "Отбасы атауы",
    familyNamePlaceholder: "Мысалы: Айсұлудың отбасы",
    createFamily: "Отбасы құру",
    creatingFamily: "Құрып жатырмыз…",
    createFamilyFailed: "Отбасы құру мүмкін болмады. Қайта көріңіз.",
    switchFamily: "Отбасын ауыстыру",
    currentFamily: "Ағымдағы отбасы",
    roleOwner: "Иесі",
    roleEditor: "Редактор",
    roleViewer: "Бақылаушы",
    recordingNotAllowed: "Сіздің рөліңізде бұл отбасына жазуға рұқсат жоқ.",
  },
} as const;

export type TranslationKey = keyof (typeof ui)["ru"];

type ContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
  greetingForHour: (hour: number) => string;
};

const I18nContext = createContext<ContextValue | null>(null);

/**
 * Which greeting belongs to an hour of the day.
 *
 * Four parts, not three. The old ladder was `hour < 12 ? morning : ...`, so
 * everything from midnight onwards was «Доброе утро» — and 00:04 is exactly
 * when someone sits up talking with a grandparent, which is the moment this
 * product is built for.
 *
 * Pure and exported so the boundaries can be tested at every hour rather than
 * at whatever time the suite happens to run.
 */
export function greetingKeyForHour(
  hour: number,
): "goodNight" | "goodMorning" | "goodAfternoon" | "goodEvening" {
  if (hour < 5) return "goodNight";
  if (hour < 12) return "goodMorning";
  if (hour < 18) return "goodAfternoon";
  if (hour < 23) return "goodEvening";
  return "goodNight";
}

export function MuraI18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("ru");

  useEffect(() => {
    const stored = window.localStorage.getItem("mura-locale");
    if (stored === "ru" || stored === "kk") setLocaleState(stored);
  }, []);

  const setLocale = (next: Locale) => {
    setLocaleState(next);
    window.localStorage.setItem("mura-locale", next);
  };

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<ContextValue>(() => {
    const t = (key: TranslationKey, vars: Record<string, string | number> = {}) =>
      Object.entries(vars).reduce(
        (text, [name, replacement]) => text.replace(`{${name}}`, String(replacement)),
        ui[locale][key] as string,
      );
    const greetingForHour = (hour: number) => t(greetingKeyForHour(hour));
    return { locale, setLocale, t, greetingForHour };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useMuraI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useMuraI18n must be used inside MuraI18nProvider");
  return value;
}

/**
 * Language control, placed by whoever owns the chrome.
 *
 * It used to be `fixed` with its offset computed from the old 430px column
 * (`calc((100vw-430px)/2+16px)`), so it tracked a container that no longer
 * exists. Now the shell says where it goes: inline in the desktop rail, and
 * floating only where there is no rail to host it.
 */
export function LanguageSwitcher({
  variant = "floating",
}: {
  variant?: "floating" | "inline";
}) {
  const { locale, setLocale } = useMuraI18n();

  const floating = variant === "floating";

  // Density by context, not one size everywhere. The floating pill is a thumb
  // target on a phone and clears 44px; the rail and settings copies are
  // pointer-first and can be quieter without becoming hard to hit.
  const position = floating
    ? "fixed right-4 top-[max(env(safe-area-inset-top),12px)] z-[70] flex shadow-soft backdrop-blur"
    : "flex w-full";

  return (
    <div className={`${position} rounded-full bg-raised/90 p-1`}>
      {(["ru", "kk"] as const).map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => setLocale(item)}
          aria-pressed={locale === item}
          className={`flex items-center justify-center rounded-full px-4 text-caption font-bold tracking-[0.08em] transition-colors ${
            floating ? "min-h-11" : "min-h-9 flex-1"
          } ${locale === item ? "bg-ink text-raised" : "text-muted"}`}
        >
          {item === "ru" ? "РУС" : "ҚАЗ"}
        </button>
      ))}
    </div>
  );
}
