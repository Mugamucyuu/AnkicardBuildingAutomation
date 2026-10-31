# 词汇标签表 v0.4

更新：2026-10-31。英文标签统一；JSON 是产品初始表，运行时与 Anki 当前标签合并。已接入生成、标签修复与导入前校验，尚未迁移旧 Anki。

## 标注原则

- 每个词义必须有词性，只分 noun、verb、adjective、adverb、affix、other。
- 日语、韩语每个词义必须有 origin；英语禁止 origin。固有 native、外来 loanword、汉字词 sino。汉字表记不等于汉字词，例如桜（さくら）为 native。
- 混合构件同时打多个来源标签，逐个记录构件理由：テレビ局 → loanword（テレビ）＋ sino（局）。历史词源不确定可以明确说明，但不应因此遗漏可判断的现代分类；确实无法分类时不猜测，阻止发布并补资料。
- domain 描述词义的主题和指称对象，不要求专业语体。peninsula 属 geography；桜 的樱树／樱花义属 plants，冒充顾客义不属 plants。不能根据例句或联想归类，如 albino 不因能描述动物就属 agriculture。
- 中性常用词不标 register；日常会话可用、常见或当地简称不等于 informal。peninsula 一般义不标 informal。
- regional 只标地域限定用法，不标标准语；medium 已删除。
- 新增植物主题 domain::nature::plants；domain::nature 仅分组，不输出。地理扩展现有 domain::social_science::geography，不另建重复分类。模型自行新增领域最多三段，computing、electronics、linguistics 不再细分；用户在 Anki 已建立的更深子标签可直接复用。
- 生成后模型复核可补标、纠错、删标；只能用允许标签，修正后的每个标签必须有理由。不会改写讲解。必填项不可删空，失败则重试并阻止发布。
- AI 新提案目前需审核，不自动写全局表；新旧标签表版本不兼容，旧预览应重新审核，不只修改版本号。当前已有 Anki 数据不自动迁移。

## 完整标签表

以下仅列产品初始标签。运行时还会加入 Anki 英文用户标签、父级结构和可选用户说明；生成与复核共用 [标注原则](../../prompts/tagging_policy.txt)，参见 [同步方式与配置](../../docs/FRAMEWORK.md#从-anki-同步标签)。

### pos — 词性

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| pos::noun | 名词 | 指称实体、事件或抽象概念的名词。 | * |
| pos::verb | 动词 | 动作、过程或状态动词。 | * |
| pos::adjective | 形容词 | 描述性质或状态。 | * |
| pos::adverb | 副词 | 修饰谓词、性质或整个句子。 | * |
| pos::affix | 词缀 | 作为学习条目收录的前缀或后缀。 | * |
| pos::other | 其他词性 | 已确认的其他词性，如代词、数词、限定词、助词、助动词、介词类、连词、感叹词或独立收录的黏着词根；未知词性不归此类。 | * |

### origin — 语源

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| origin::native | 固有词 | 日语和语或韩语固有语；不能按文字外观判定。 | ja,ko |
| origin::loanword | 外来词 | 按目标语言词典惯例归为外来语；历史上源自汉语不自动归到此类。 | ja,ko |
| origin::sino | 汉字词 | 日语汉语／韩语汉字语；包括词典如此分类的本土汉字造词。 | ja,ko |

### domain — 主题与专业领域

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| domain::daily_life | 日常生活 | 日常起居相关词义。 | * |
| domain::daily_life::food | 饮食 | 食物、烹饪与饮食行为。 | * |
| domain::daily_life::housing | 居住 | 住房、家具与家务。 | * |
| domain::daily_life::clothing | 服饰 | 衣物、穿搭与纺织用品。 | * |
| domain::daily_life::shopping | 购物 | 购物、商品与消费活动。 | * |
| domain::daily_life::travel | 旅行 | 旅行、观光与住宿。 | * |
| domain::daily_life::transport | 交通 | 出行方式、道路与交通活动。 | * |
| domain::daily_life::relationships | 人际关系 | 家庭、友谊与社会交往。 | * |
| domain::daily_life::health | 日常健康 | 症状、保健与就医的日常表达；医学术语可同时标 medicine。 | * |
| domain::daily_life::work | 工作生活 | 求职、办公与职场日常。 | * |
| domain::daily_life::leisure | 休闲 | 娱乐、兴趣与休闲活动。 | * |
| domain::sports | 运动 | 体育项目、训练和竞赛术语。 | * |
| domain::sports::football | 足球 | 足球运动专门含义。 | * |
| domain::sports::basketball | 篮球 | 篮球运动专门含义。 | * |
| domain::sports::baseball | 棒球 | 棒球运动专门含义。 | * |
| domain::sports::tennis | 网球 | 网球运动专门含义。 | * |
| domain::sports::swimming | 游泳 | 游泳运动专门含义。 | * |
| domain::sports::athletics | 田径 | 跑、跳、投等田径运动。 | * |
| domain::sports::martial_arts | 武术与格斗 | 武术、武道及格斗运动。 | * |
| domain::sports::fitness | 健身 | 体能训练和健身活动。 | * |
| domain::sports::winter_sports | 冬季运动 | 滑雪、滑冰等冬季运动。 | * |
| domain::arts | 艺术 | 艺术创作、作品与鉴赏。 | * |
| domain::arts::music | 音乐 | 音乐创作、表演与鉴赏。 | * |
| domain::arts::literature | 文学 | 文学创作、体裁和研究；不等于 literary 语体。 | * |
| domain::arts::visual_arts | 视觉艺术 | 绘画、雕塑等视觉艺术。 | * |
| domain::arts::film | 电影 | 电影制作、影像与电影研究。 | * |
| domain::arts::theatre | 戏剧 | 舞台戏剧及表演。 | * |
| domain::arts::dance | 舞蹈 | 舞种、动作与编舞。 | * |
| domain::arts::photography | 摄影 | 摄影器材与摄影技法。 | * |
| domain::arts::design | 设计 | 设计实践、方法与视觉传达。 | * |
| domain::business | 商业 | 经营、交易与企业活动。 | * |
| domain::business::management | 管理 | 组织、运营与管理术语。 | * |
| domain::business::marketing | 营销 | 市场研究、广告与推广。 | * |
| domain::business::sales | 销售 | 销售流程、渠道与客户关系。 | * |
| domain::business::accounting | 会计 | 记账、报表和审计。 | * |
| domain::business::finance | 金融 | 资金、投资及金融市场。 | * |
| domain::business::trade | 贸易 | 国内及国际贸易。 | * |
| domain::business::logistics | 物流 | 运输、仓储及供应链。 | * |
| domain::business::human_resources | 人力资源 | 招聘、薪酬与员工管理。 | * |
| domain::business::entrepreneurship | 创业 | 创业、融资与企业设立。 | * |
| domain::science | 自然与形式科学 | 科学概念及研究。 | * |
| domain::science::mathematics | 数学 | 数学概念、方法与研究。 | * |
| domain::science::statistics | 统计学 | 统计推断、估计和数据分析。 | * |
| domain::science::physics | 物理学 | 物质、能量及其规律。 | * |
| domain::science::chemistry | 化学 | 物质组成、结构及反应。 | * |
| domain::science::biology | 生物学 | 生命系统、结构与过程。 | * |
| domain::science::earth_science | 地球科学 | 地球结构及自然过程。 | * |
| domain::science::astronomy | 天文学 | 天体及宇宙研究。 | * |
| domain::technology | 技术与工程 | 技术系统、工程方法与实践。 | * |
| domain::technology::computing | 计算机技术 | 计算系统、软件与网络。 | * |
| domain::technology::electronics | 电子工程 | 电子器件、电路及系统。 | * |
| domain::technology::mechanical_engineering | 机械工程 | 机械结构、动力及制造。 | * |
| domain::technology::civil_engineering | 土木工程 | 建筑结构、道路及基础设施。 | * |
| domain::technology::materials | 材料工程 | 材料性能、加工与应用。 | * |
| domain::technology::energy | 能源技术 | 能源转换、储存与供应。 | * |
| domain::technology::telecommunications | 通信工程 | 通信信号、链路与系统。 | * |
| domain::medicine | 医学 | 疾病、诊断、治疗及医学研究。 | * |
| domain::medicine::anatomy | 解剖学 | 身体结构及器官。 | * |
| domain::medicine::physiology | 生理学 | 机体功能与调节。 | * |
| domain::medicine::pharmacology | 药理学 | 药物作用与应用。 | * |
| domain::medicine::mental_health | 精神健康 | 精神疾病、心理健康及干预。 | * |
| domain::medicine::public_health | 公共卫生 | 群体健康、预防和卫生政策。 | * |
| domain::humanities | 人文学科 | 语言、历史、思想与文化研究。 | * |
| domain::humanities::linguistics | 语言学 | 语言结构、使用与演变。 | * |
| domain::humanities::history | 历史 | 历史事件、制度与研究。 | * |
| domain::humanities::philosophy | 哲学 | 知识、存在、伦理及思想。 | * |
| domain::humanities::religion | 宗教 | 信仰、仪式及宗教研究。 | * |
| domain::humanities::archaeology | 考古学 | 遗存、发掘及古代社会。 | * |
| domain::social_science | 社会科学 | 社会结构、行为与制度研究。 | * |
| domain::social_science::economics | 经济学 | 资源分配、生产与经济机制。 | * |
| domain::social_science::law | 法律 | 法律制度、规则与诉讼。 | * |
| domain::social_science::politics | 政治学 | 权力、治理与政治制度。 | * |
| domain::social_science::sociology | 社会学 | 社会关系、组织与变迁。 | * |
| domain::social_science::psychology | 心理学 | 认知、情绪与行为研究。 | * |
| domain::social_science::education | 教育学 | 教学、学习及教育制度。 | * |
| domain::social_science::anthropology | 人类学 | 人类文化、社会及演化。 | * |
| domain::social_science::geography | 地理学 | 地貌、半岛、河流、山脉、区域与空间关系；包括日常地理名称，不限专业术语。 | * |
| domain::media | 媒体与传播 | 信息传播、新闻与公共表达。 | * |
| domain::media::journalism | 新闻 | 采访、报道及新闻工作。 | * |
| domain::media::internet_culture | 网络文化 | 网络社群、平台文化及网络表达。 | * |
| domain::games | 游戏 | 游戏机制、玩法与社群术语。 | * |
| domain::games::video_games | 电子游戏 | 电子游戏系统及玩法。 | * |
| domain::games::board_games | 桌面游戏 | 桌游、棋类及卡牌游戏。 | * |
| domain::environment | 环境 | 环境保护、污染及可持续发展。 | * |
| domain::agriculture | 农业 | 种植、养殖与农业生产。 | * |
| domain::military | 军事 | 军队、武器与军事行动。 | * |
| domain::nature | 自然主题 | 自然事物的主题分组。 | * |
| domain::nature::plants | 植物 | 植物、树木、花卉及其名称；包括日常用词，不要求植物学专业语体。 | * |

### context — 使用场景

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| context::personal | 私人生活 | 主要用于家庭、私人关系或个人事务的表达；不是所有词都默认添加。 | * |
| context::public | 公共事务 | 主要用于公共服务、社会参与或公共交往的表达。 | * |
| context::educational | 学习教育 | 主要用于课堂、教学或学习活动的表达。 | * |
| context::occupational | 职业工作 | 主要用于工作任务和职业交往的表达。 | * |

### register — 语体

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| register::formal | 正式 | 受正式场合或规范表达偏好的用法。 | * |
| register::informal | 非正式 | 词本身明显限于随意、非正式语境；日常可用、常见或中性不等于非正式。 | * |
| register::colloquial | 日常口语 | 典型日常会话表达；不等于所有可说出口的词。 | * |
| register::slang | 俚语 | 特定社群或潮流中的非正式表达；不等于一般口语。 | * |
| register::literary | 文学性 | 具有文学风格的词义；不是所有文学研究术语。 | * |
| register::academic | 学术 | 具有学术论述语体特征；不是所有学科术语。 | * |
| register::technical | 专业术语 | 具有特定专业定义或专门使用范围。 | * |
| register::bureaucratic | 公文行政 | 典型行政、公文或官僚表达。 | * |

### time — 时代与时效

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| time::archaic | 古语 | 当代一般使用中已明显古旧，但可能保留在文艺或固定表达中。 | * |
| time::dated | 过时表达 | 仍可理解但显露较早时代的用语。 | * |
| time::obsolete | 废用语 | 现代一般用法中已不再使用；须有词典证据。 | * |
| time::historical | 历史事物 | 指历史制度、器物等；不表示词本身已经废用。 | * |
| time::neologism | 新词新义 | 有时间依据的新近词或词义；记录判断日期，不能永久当作新词。 | * |

### regional — 地域限定用法

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| regional | 韩语地域限定用法 | 仅韩语：明确受地域限制的用法；标准语或通用词不标。 | ko |
| regional::uk | 英国限定 | 明确限于或明显特属于英国的用法；英美通用词不标。 | en |
| regional::us | 美国限定 | 明确限于或明显特属于美国的用法；美式发音偏好不是地域限定。 | en |
| regional::other | 其他地区限定 | 英语英美以外或日语关西以外的地域限定用法；具体地区另存。 | en,ja |
| regional::kansai | 关西限定 | 日语明确的关西地域用法。 | ja |

### connotation — 评价与感情色彩

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| connotation::approving | 褒义 | 表达赞许或积极评价；不是仅指好事。 | * |
| connotation::disapproving | 贬义 | 表达不赞许或负面评价；不是仅指坏事。 | * |
| connotation::derogatory | 蔑称 | 贬低、轻蔑地称呼人或群体。 | * |
| connotation::affectionate | 亲昵 | 带有亲近、疼爱或友善色彩。 | * |
| connotation::humorous | 诙谐 | 惯常用于幽默或戏谑表达。 | * |
| connotation::ironic | 反讽 | 具有约定俗成的反讽用法；不能根据任意反讽例句推广。 | * |
| connotation::euphemistic | 委婉 | 用于缓和、回避直接说法的表达。 | * |

### sensitivity — 冒犯与禁忌

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| sensitivity::vulgar | 粗俗 | 被认为粗鄙的表达；未必专门攻击对象。 | * |
| sensitivity::offensive | 冒犯性 | 可能冒犯听者或特定对象的词义。 | * |
| sensitivity::taboo | 禁忌 | 在相关文化中受到强烈使用限制的表达。 | * |
| sensitivity::slur | 歧视性蔑称 | 针对身份或群体的侮辱性称呼，要求可靠用法证据。 | * |

### politeness — 礼貌与敬语

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| politeness::polite | 礼貌表达 | 词汇化或固定的礼貌用语，非仅某例句加了礼貌词尾。 | * |
| politeness::honorific | 尊敬表达 | 词汇本身具有抬高所指人物的尊敬功能。 | * |
| politeness::humble | 谦让表达 | 词汇本身通过自谦表达对他人的尊重。 | * |
| politeness::rude | 失礼表达 | 词汇本身具有明显不礼貌或冒犯交际规范的特征。 | * |

### form — 词条形式

| 标签 | 中文 | 边界 | 语言 |
|---|---|---|---|
| form::single_word | 单词 | 作为单一词汇单位收录的词；不可只按空格判断。 | * |
| form::multiword_expression | 多词表达 | 由多个词形成的惯用学习单位。 | * |
| form::multiword_expression::idiom | 习语 | 整体意义不能直接由各组成部分推得的固定表达。 | * |
| form::multiword_expression::collocation | 搭配 | 具有常见共现习惯的词组。 | * |
| form::multiword_expression::phrasal_verb | 短语动词 | 词典认定的动词与小品词组合。 | * |
| form::multiword_expression::proverb | 谚语 | 表达一般经验或道理的固定句式。 | * |
| form::multiword_expression::fixed_expression | 固定表达 | 惯用固定表达，不一定是习语。 | * |
| form::abbreviation | 缩写 | 缩略形式的上位类别。 | * |
| form::abbreviation::acronym | 首字母成词 | 可作为词读出的首字母缩略形式。 | * |
| form::abbreviation::initialism | 首字母逐字读 | 按字母逐个读出的缩略形式。 | * |
| form::abbreviation::clipping | 截短词 | 通过截短词形产生的词。 | * |
| form::onomatopoeia | 拟声拟态 | 模拟声音或状态的表达，具体类别用子标签区分。 | * |
| form::onomatopoeia::sound_symbolic | 拟声 | 直接模拟声音的表达。 | * |
| form::onomatopoeia::mimetic | 拟态 | 模拟状态、动作或感觉的表达。 | * |

## 参考资料

- [Universal Dependencies: Universal POS tags](https://universaldependencies.org/u/pos/all.html)
- [Oxford Learner's Dictionaries: Labels](https://www.oxfordlearnersdictionaries.com/about/english/labels)
- [Council of Europe: CEFR](https://www.coe.int/en/web/portfolio/the-common-european-framework-of-reference-for-languages-learning-teaching-assessment-cefr-)
- [NINJAL: UniDic 中古和文标注规范](https://clrd.ninjal.ac.jp/chj/doc/unidic-MLJ_rulebook_v1_1.pdf)
- [National Institute of Korean Language: Korean Basic Dictionary Open API](https://krdict.korean.go.kr/kor/openApi/openApiInfo)
- [Anki Manual: Searching](https://docs.ankiweb.net/searching.html)
- [Anki Manual: Filtered Decks](https://docs.ankiweb.net/filtered-decks.html)
