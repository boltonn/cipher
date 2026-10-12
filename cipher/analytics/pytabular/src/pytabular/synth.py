"""Synthetic messy tables with known column types, for comparing detectors.

Each scenario (subscribers, call records, transfers, staff lists, contacts, network
logs, registries) is rendered in a random header language and style: snake_case,
camelCase, abbreviated, title rows above the header, no header at all, plus nulls,
shuffled columns, junk columns and mixed value formats. Values come from small
multilingual name and place lists and checksum-valid selectors.
"""

import csv
import json
import random
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

GIVEN = {
    "en": [
        "James",
        "Mary",
        "John",
        "Patricia",
        "Robert",
        "Jennifer",
        "Michael",
        "Linda",
        "William",
        "Elizabeth",
        "David",
        "Susan",
    ],
    "ru": [
        "Иван",
        "Мария",
        "Алексей",
        "Анна",
        "Дмитрий",
        "Елена",
        "Сергей",
        "Ольга",
        "Андрей",
        "Наталья",
        "Николай",
        "Татьяна",
    ],
    "zh": ["伟", "芳", "娜", "敏", "静", "强", "磊", "洋", "艳", "勇"],
    "ar": ["محمد", "أحمد", "فاطمة", "علي", "مريم", "حسن", "زينب", "عمر"],
    "fr": ["Jean", "Marie", "Pierre", "Sophie", "Luc", "Camille", "Nicolas", "Julie"],
    "es": ["José", "María", "Carlos", "Lucía", "Javier", "Carmen", "Miguel", "Elena"],
}
SURNAME = {
    "en": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", "Taylor", "Clark"],
    "ru": ["Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Федоров"],
    "zh": ["王", "李", "张", "刘", "陈", "杨", "黄", "赵", "吴", "周"],
    "ar": ["الحسيني", "العلي", "حداد", "خوري", "منصور", "سليمان", "يوسف", "نصر"],
    "fr": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand"],
    "es": ["García", "Fernández", "González", "Rodríguez", "López", "Martínez", "Sánchez", "Pérez"],
}
PATRONYMIC = ["Иванович", "Петрович", "Сергеевна", "Алексеевич", "Дмитриевна", "Николаевич", "Андреевна"]
ORGS = {
    "en": [
        "Acme Ltd",
        "Northwind Trading LLC",
        "Globex Corporation",
        "Initech Inc",
        "First City Bank",
        "Blue Ocean Holdings",
    ],
    "ru": ['ООО "Ромашка"', "ПАО Сбербанк", 'АО "Техснаб"', 'ООО "Вектор"', "ЗАО Альфа-Строй", "ИП Петров А.В."],
    "zh": ["华为技术有限公司", "中国银行", "阿里巴巴集团", "腾讯科技有限公司", "上海贸易公司"],
    "ar": ["شركة النور للتجارة", "بنك الخليج", "شركة الأمل", "مؤسسة الفجر"],
    "fr": ["Société Générale", "Durand SARL", "Atelier Martin SAS", "Banque Populaire"],
    "es": ["Banco Santander", "Construcciones López SL", "Grupo Herrera SA", "Transportes Ruiz"],
}
STREETS = {
    "en": ["{n} Main St", "{n} Oak Avenue", "{n} Park Rd", "{n} Elm Street, Apt {u}"],
    "ru": ["ул. Ленина, д. {n}, кв. {u}", "пр-т Мира, д. {n}", "ул. Гагарина, д. {n}, корп. 2", "Тверская ул., {n}"],
    "zh": ["中山路{n}号", "人民路{n}号{u}室", "建国路{n}号"],
    "ar": ["شارع الملك فهد {n}", "شارع الجمهورية {n}"],
    "fr": ["{n} rue de la Paix", "{n} avenue Victor Hugo", "{n} boulevard Saint-Michel"],
    "es": ["Calle Mayor {n}", "Avenida de la Constitución {n}", "Calle Alcalá {n}, piso {u}"],
}
NATIONALITY = {
    "en": ["Russian", "American", "Chinese", "French", "Iranian", "German", "Ukrainian"],
    "ru": ["Россия", "РФ", "Украина", "Казахстан", "русский", "гражданин РФ"],
    "zh": ["中国", "俄罗斯", "美国"],
    "ar": ["سوري", "عراقي", "مصري", "لبناني"],
    "fr": ["française", "Russe", "Allemand"],
    "es": ["español", "Mexicano", "Ruso"],
}
REGION = {"en": "US", "ru": "RU", "zh": "CN", "ar": "EG", "fr": "FR", "es": "ES"}
CITIES = {
    "en": ["New York", "London", "Chicago", "Toronto", "Sydney", "Boston", "Dubai"],
    "ru": ["Москва", "Санкт-Петербург", "Новосибирск", "Казань", "Екатеринбург", "Киев", "Минск"],
    "zh": ["北京", "上海", "广州", "深圳", "成都", "武汉"],
    "ar": ["القاهرة", "دمشق", "بغداد", "بيروت", "عمان", "الرياض"],
    "fr": ["Paris", "Lyon", "Marseille", "Toulouse", "Bordeaux", "Lille"],
    "es": ["Madrid", "Barcelona", "Sevilla", "Valencia", "Bilbao", "Málaga"],
}
COUNTRIES = {
    "en": ["Russia", "United States", "China", "France", "Germany", "Iran", "Ukraine"],
    "ru": ["Россия", "Украина", "Казахстан", "Беларусь", "Германия", "Китай"],
    "zh": ["中国", "俄罗斯", "美国", "日本", "法国"],
    "ar": ["مصر", "سوريا", "العراق", "لبنان", "الأردن"],
    "fr": ["France", "Allemagne", "Espagne", "Belgique", "Suisse"],
    "es": ["España", "México", "Argentina", "Colombia", "Chile"],
}
CRYPTO = [
    "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq",
    "0x52908400098527886E0F7030069857D2E4169EE7",
    "0xde709f2102306220921060314715629080e2fb77",
    "3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
]

HEADERS: dict[str, dict[str, list[str]]] = {
    "person.full_name": {
        "en": ["Name", "Full Name", "Customer", "Subscriber"],
        "ru": ["ФИО", "Ф.И.О.", "Абонент"],
        "zh": ["姓名"],
        "ar": ["الاسم"],
        "fr": ["Nom complet"],
        "es": ["Nombre completo"],
    },
    "person.given_name": {
        "en": ["First Name", "Given"],
        "ru": ["Имя"],
        "zh": ["名"],
        "ar": ["الاسم الأول"],
        "fr": ["Prénom"],
        "es": ["Nombre"],
    },
    "person.surname": {
        "en": ["Last Name", "Surname"],
        "ru": ["Фамилия"],
        "zh": ["姓"],
        "ar": ["اسم العائلة"],
        "fr": ["Nom de famille"],
        "es": ["Apellido"],
    },
    "person.patronymic": {
        "en": ["Middle Name"],
        "ru": ["Отчество"],
        "zh": ["中间名"],
        "ar": ["اسم الأب"],
        "fr": ["Second prénom"],
        "es": ["Segundo nombre"],
    },
    "person.date_of_birth": {
        "en": ["DOB", "Date of Birth", "Birthdate"],
        "ru": ["Дата рождения", "Д.Р."],
        "zh": ["出生日期"],
        "ar": ["تاريخ الميلاد"],
        "fr": ["Date de naissance"],
        "es": ["Fecha de nacimiento"],
    },
    "person.age": {"en": ["Age"], "ru": ["Возраст"], "zh": ["年龄"], "ar": ["العمر"], "fr": ["Âge"], "es": ["Edad"]},
    "person.gender": {
        "en": ["Sex", "Gender"],
        "ru": ["Пол"],
        "zh": ["性别"],
        "ar": ["الجنس"],
        "fr": ["Sexe"],
        "es": ["Sexo"],
    },
    "person.nationality": {
        "en": ["Nationality", "Citizenship"],
        "ru": ["Гражданство"],
        "zh": ["国籍"],
        "ar": ["الجنسية"],
        "fr": ["Nationalité"],
        "es": ["Nacionalidad"],
    },
    "person.occupation": {
        "en": ["Position", "Job Title"],
        "ru": ["Должность"],
        "zh": ["职位"],
        "ar": ["الوظيفة"],
        "fr": ["Poste"],
        "es": ["Cargo"],
    },
    "organization.name": {
        "en": ["Company", "Employer", "Organization"],
        "ru": ["Организация", "Место работы"],
        "zh": ["公司", "单位"],
        "ar": ["الشركة"],
        "fr": ["Entreprise"],
        "es": ["Empresa"],
    },
    "location.address": {
        "en": ["Address", "Home Address"],
        "ru": ["Адрес", "Адрес регистрации"],
        "zh": ["地址"],
        "ar": ["العنوان"],
        "fr": ["Adresse"],
        "es": ["Dirección"],
    },
    "location.city": {
        "en": ["City", "Town"],
        "ru": ["Город"],
        "zh": ["城市"],
        "ar": ["المدينة"],
        "fr": ["Ville"],
        "es": ["Ciudad"],
    },
    "location.country": {
        "en": ["Country"],
        "ru": ["Страна"],
        "zh": ["国家"],
        "ar": ["الدولة"],
        "fr": ["Pays"],
        "es": ["País"],
    },
    "location.country_code": {
        "en": ["Country Code", "CC"],
        "ru": ["Код страны"],
        "zh": ["国家代码"],
        "ar": ["رمز البلد"],
        "fr": ["Code pays"],
        "es": ["Código de país"],
    },
    "location.postal_code": {
        "en": ["ZIP", "Postcode"],
        "ru": ["Индекс"],
        "zh": ["邮编"],
        "ar": ["الرمز البريدي"],
        "fr": ["Code postal"],
        "es": ["Código postal"],
    },
    "location.latitude": {
        "en": ["Lat", "Latitude"],
        "ru": ["Широта"],
        "zh": ["纬度"],
        "ar": ["خط العرض"],
        "fr": ["Latitude"],
        "es": ["Latitud"],
    },
    "location.longitude": {
        "en": ["Lon", "Longitude", "Lng"],
        "ru": ["Долгота"],
        "zh": ["经度"],
        "ar": ["خط الطول"],
        "fr": ["Longitude"],
        "es": ["Longitud"],
    },
    "location.coordinate": {
        "en": ["GPS", "Coordinates"],
        "ru": ["Координаты"],
        "zh": ["坐标"],
        "ar": ["الإحداثيات"],
        "fr": ["Coordonnées"],
        "es": ["Coordenadas"],
    },
    "selector.phone": {
        "en": ["Phone", "Mobile", "Tel."],
        "ru": ["Телефон", "Моб. тел."],
        "zh": ["手机号码", "电话"],
        "ar": ["رقم الهاتف"],
        "fr": ["Téléphone"],
        "es": ["Teléfono"],
    },
    "selector.email": {
        "en": ["Email", "E-mail Address"],
        "ru": ["Эл. почта", "E-mail"],
        "zh": ["邮箱"],
        "ar": ["البريد الإلكتروني"],
        "fr": ["Courriel"],
        "es": ["Correo"],
    },
    "selector.ip": {
        "en": ["IP", "Source IP"],
        "ru": ["IP-адрес"],
        "zh": ["IP地址"],
        "ar": ["عنوان IP"],
        "fr": ["Adresse IP"],
        "es": ["Dirección IP"],
    },
    "selector.iban": {
        "en": ["IBAN", "Account"],
        "ru": ["Счет", "IBAN"],
        "zh": ["账号"],
        "ar": ["رقم الحساب"],
        "fr": ["IBAN"],
        "es": ["Cuenta"],
    },
    "selector.bank_card": {
        "en": ["Card Number", "PAN"],
        "ru": ["Номер карты"],
        "zh": ["卡号"],
        "ar": ["رقم البطاقة"],
        "fr": ["Numéro de carte"],
        "es": ["Tarjeta"],
    },
    "selector.passport": {
        "en": ["Passport No"],
        "ru": ["Паспорт", "Серия и номер паспорта"],
        "zh": ["护照号码"],
        "ar": ["رقم الجواز"],
        "fr": ["Passeport"],
        "es": ["Pasaporte"],
    },
    "selector.imei": {"en": ["IMEI"], "ru": ["IMEI"], "zh": ["IMEI"], "ar": ["IMEI"], "fr": ["IMEI"], "es": ["IMEI"]},
    "selector.social_handle": {
        "en": ["Telegram", "Handle"],
        "ru": ["Телеграм", "Ник"],
        "zh": ["微信"],
        "ar": ["حساب"],
        "fr": ["Pseudo"],
        "es": ["Perfil"],
    },
    "selector.crypto_address": {
        "en": ["Wallet"],
        "ru": ["Кошелек"],
        "zh": ["钱包地址"],
        "ar": ["محفظة"],
        "fr": ["Portefeuille"],
        "es": ["Billetera"],
    },
    "selector.domain": {
        "en": ["Website", "URL"],
        "ru": ["Сайт"],
        "zh": ["网站"],
        "ar": ["الموقع"],
        "fr": ["Site web"],
        "es": ["Sitio web"],
    },
    "selector.mac_address": {
        "en": ["MAC"],
        "ru": ["MAC-адрес"],
        "zh": ["MAC地址"],
        "ar": ["MAC"],
        "fr": ["Adresse MAC"],
        "es": ["MAC"],
    },
    "time.datetime": {
        "en": ["Timestamp", "Date/Time"],
        "ru": ["Дата и время"],
        "zh": ["时间"],
        "ar": ["الوقت"],
        "fr": ["Horodatage"],
        "es": ["Fecha y hora"],
    },
    "time.date": {"en": ["Date"], "ru": ["Дата"], "zh": ["日期"], "ar": ["التاريخ"], "fr": ["Date"], "es": ["Fecha"]},
    "time.epoch": {"en": ["ts", "Unix Time"], "ru": ["ts"], "zh": ["ts"], "ar": ["ts"], "fr": ["ts"], "es": ["ts"]},
    "time.duration": {
        "en": ["Duration", "Call Length"],
        "ru": ["Длительность"],
        "zh": ["通话时长"],
        "ar": ["المدة"],
        "fr": ["Durée"],
        "es": ["Duración"],
    },
    "edge.amount": {
        "en": ["Amount"],
        "ru": ["Сумма"],
        "zh": ["金额"],
        "ar": ["المبلغ"],
        "fr": ["Montant"],
        "es": ["Importe"],
    },
    "edge.currency": {
        "en": ["Currency", "CCY"],
        "ru": ["Валюта"],
        "zh": ["币种"],
        "ar": ["العملة"],
        "fr": ["Devise"],
        "es": ["Moneda"],
    },
    "edge.direction": {
        "en": ["Direction", "Call Type"],
        "ru": ["Направление"],
        "zh": ["呼叫类型"],
        "ar": ["الاتجاه"],
        "fr": ["Sens"],
        "es": ["Dirección"],
    },
    "key.row_id": {"en": ["ID", "#"], "ru": ["№", "ID"], "zh": ["序号"], "ar": ["رقم"], "fr": ["ID"], "es": ["ID"]},
    "key.reference": {
        "en": ["Reference", "Transaction ID"],
        "ru": ["Номер операции"],
        "zh": ["参考号"],
        "ar": ["المرجع"],
        "fr": ["Référence"],
        "es": ["Referencia"],
    },
    "other.free_text": {
        "en": ["Notes", "Comment"],
        "ru": ["Примечание"],
        "zh": ["备注"],
        "ar": ["ملاحظات"],
        "fr": ["Remarques"],
        "es": ["Notas"],
    },
    "other.boolean": {
        "en": ["Active"],
        "ru": ["Активен"],
        "zh": ["有效"],
        "ar": ["نشط"],
        "fr": ["Actif"],
        "es": ["Activo"],
    },
    "other.category": {
        "en": ["Status"],
        "ru": ["Статус"],
        "zh": ["状态"],
        "ar": ["الحالة"],
        "fr": ["Statut"],
        "es": ["Estado"],
    },
}
ROLE_WORDS = {
    "sender": {
        "en": "Sender",
        "ru": "отправителя",
        "zh": "发送方",
        "ar": "المرسل",
        "fr": "expéditeur",
        "es": "remitente",
    },
    "receiver": {
        "en": "Receiver",
        "ru": "получателя",
        "zh": "接收方",
        "ar": "المستلم",
        "fr": "destinataire",
        "es": "destinatario",
    },
    "caller": {"en": "Caller", "ru": "звонящего", "zh": "主叫", "ar": "المتصل", "fr": "appelant", "es": "llamante"},
    "callee": {"en": "Called", "ru": "вызываемого", "zh": "被叫", "ar": "المتلقي", "fr": "appelé", "es": "llamado"},
}

# (field type, role) per column; the role becomes a header prefix/suffix.
SCENARIOS: dict[str, list[tuple[str, str | None]]] = {
    "subscribers": [
        ("key.row_id", None),
        ("person.full_name", None),
        ("person.date_of_birth", None),
        ("selector.phone", None),
        ("selector.email", None),
        ("location.address", None),
        ("person.nationality", None),
        ("selector.passport", None),
    ],
    "call_records": [
        ("selector.phone", "caller"),
        ("selector.phone", "callee"),
        ("time.datetime", None),
        ("time.duration", None),
        ("selector.imei", None),
        ("location.latitude", None),
        ("location.longitude", None),
        ("edge.direction", None),
    ],
    "transfers": [
        ("key.reference", None),
        ("person.full_name", "sender"),
        ("selector.iban", "sender"),
        ("person.full_name", "receiver"),
        ("selector.iban", "receiver"),
        ("edge.amount", None),
        ("edge.currency", None),
        ("time.date", None),
    ],
    "staff": [
        ("person.surname", None),
        ("person.given_name", None),
        ("person.patronymic", None),
        ("person.gender", None),
        ("organization.name", None),
        ("person.occupation", None),
        ("location.city", None),
        ("location.country", None),
        ("location.postal_code", None),
    ],
    "contacts": [
        ("person.full_name", None),
        ("selector.phone", None),
        ("selector.email", None),
        ("selector.social_handle", None),
        ("selector.crypto_address", None),
        ("other.free_text", None),
        ("other.category", None),
    ],
    "network_log": [
        ("selector.email", None),
        ("selector.ip", None),
        ("selector.mac_address", None),
        ("time.epoch", None),
        ("selector.domain", None),
        ("other.boolean", None),
    ],
    "registry": [
        ("person.full_name", None),
        ("person.age", None),
        ("person.gender", None),
        ("location.country_code", None),
        ("location.coordinate", None),
        ("selector.bank_card", None),
        ("organization.name", None),
    ],
}


@dataclass(slots=True)
class SyntheticTable:
    name: str
    path: Path
    labels: list[str]
    roles: list[str | None] = field(default_factory=list)


def _luhn(prefix: str, length: int, rng: random.Random) -> str:
    body = prefix + "".join(rng.choice(string.digits) for _ in range(length - len(prefix) - 1))
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return body + str((10 - total % 10) % 10)


def _iban(rng: random.Random) -> str:
    country, bban = rng.choice(
        [
            ("DE", "".join(rng.choice(string.digits) for _ in range(18))),
            ("GB", "NWBK" + "".join(rng.choice(string.digits) for _ in range(14))),
            ("FR", "".join(rng.choice(string.digits) for _ in range(23))),
        ]
    )
    numeric = "".join(str(int(ch, 36)) for ch in bban + country + "00")
    check = 98 - int(numeric) % 97
    return f"{country}{check:02d}{bban}"


def _phone(lang: str, rng: random.Random) -> str:
    d = lambda n: "".join(rng.choice(string.digits) for _ in range(n))  # noqa: E731
    match lang:
        case "ru":
            return rng.choice([f"+7 9{d(2)} {d(3)}-{d(2)}-{d(2)}", f"89{d(9)}", f"7 (9{d(2)}) {d(3)}-{d(4)}"])
        case "zh":
            return rng.choice([f"13{d(9)}", f"+86 138 {d(4)} {d(4)}"])
        case "ar":
            return f"+20 10{d(8)}"
        case "fr":
            return rng.choice([f"06 {d(2)} {d(2)} {d(2)} {d(2)}", f"+33 6{d(8)}"])
        case "es":
            return f"+34 6{d(2)} {d(3)} {d(3)}"
        case _:
            return rng.choice([f"(212) 555-{d(4)}", f"+1 415 {d(3)} {d(4)}", f"+44 7700 {d(6)}"])


def _date(rng: random.Random, *, start: int, end: int, style: int, with_time: bool = False) -> str:
    moment = datetime(start, 1, 1) + timedelta(
        seconds=rng.randrange(int((datetime(end, 12, 31) - datetime(start, 1, 1)).total_seconds()))
    )
    fmt = ["%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%d/%m/%Y", "%Y年%m月%d日"][style]
    if with_time:
        fmt = fmt.replace("%Y年%m月%d日", "%Y-%m-%d") + rng.choice([" %H:%M:%S", "T%H:%M:%S", " %H:%M"])
    return moment.strftime(fmt)


def value_for(field_id: str, *, lang: str, rng: random.Random, row: int, date_style: int) -> str:
    """One synthetic cell of `field_id` in a `lang` table."""
    given, surname = rng.choice(GIVEN[lang]), rng.choice(SURNAME[lang])
    d = lambda n: "".join(rng.choice(string.digits) for _ in range(n))  # noqa: E731
    match field_id:
        case "person.full_name":
            if lang == "zh":
                return surname + given
            if lang == "ru":
                return rng.choice(
                    [
                        f"{surname} {given} {rng.choice(PATRONYMIC)}",
                        f"{given} {surname}",
                        f"{surname.upper()} {given.upper()}",
                    ]
                )
            return rng.choice([f"{given} {surname}", f"{surname}, {given}", f"{given.upper()} {surname.upper()}"])
        case "person.given_name":
            return given
        case "person.surname":
            return surname
        case "person.patronymic":
            return rng.choice(PATRONYMIC) if lang == "ru" else rng.choice(GIVEN[lang])
        case "person.date_of_birth":
            return _date(rng, start=1945, end=2005, style=date_style)
        case "person.age":
            return str(rng.randint(18, 85))
        case "person.gender":
            return rng.choice(
                {
                    "ru": ["М", "Ж", "муж", "жен"],
                    "zh": ["男", "女"],
                    "ar": ["ذكر", "أنثى"],
                    "fr": ["H", "F"],
                    "es": ["H", "M"],
                }.get(lang, ["M", "F", "Male", "Female"])
            )
        case "person.nationality":
            return rng.choice(NATIONALITY[lang])
        case "person.occupation":
            return rng.choice(
                {"ru": ["Менеджер", "Бухгалтер", "Директор", "Инженер"], "zh": ["经理", "工程师", "会计"]}.get(
                    lang, ["Manager", "Engineer", "Accountant", "Director"]
                )
            )
        case "organization.name":
            return rng.choice(ORGS[lang])
        case "location.address":
            return rng.choice(STREETS[lang]).format(n=rng.randint(1, 200), u=rng.randint(1, 99))
        case "location.city":
            return rng.choice(CITIES[lang])
        case "location.country":
            return rng.choice(COUNTRIES[lang])
        case "location.country_code":
            return rng.choice(["RU", "US", "CN", "FR", "DE", "IR", "UA", "GB", "ES", "EG"])
        case "location.postal_code":
            return {"ru": d(6), "en": d(5), "fr": d(5), "es": d(5), "zh": d(6)}.get(lang, d(5))
        case "location.latitude":
            return f"{rng.uniform(-60, 70):.6f}"
        case "location.longitude":
            return f"{rng.uniform(-170, 170):.6f}"
        case "location.coordinate":
            return f"{rng.uniform(-60, 70):.5f}, {rng.uniform(-170, 170):.5f}"
        case "selector.phone":
            return _phone(lang, rng)
        case "selector.email":
            latin = "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(4, 9)))
            return f"{latin}{rng.randint(1, 999)}@{rng.choice(['gmail.com', 'mail.ru', 'yandex.ru', 'qq.com', 'outlook.com'])}"
        case "selector.ip":
            return f"{rng.randint(11, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        case "selector.iban":
            return _iban(rng)
        case "selector.bank_card":
            return _luhn(rng.choice(["4", "51", "2200"]), 16, rng)
        case "selector.passport":
            return rng.choice([f"{d(2)} {d(2)} {d(6)}", f"{rng.choice(string.ascii_uppercase)}{d(8)}"])
        case "selector.imei":
            return _luhn("35", 15, rng)
        case "selector.social_handle":
            return rng.choice(
                [f"@{rng.choice(GIVEN['en']).lower()}_{d(3)}", f"https://t.me/{rng.choice(GIVEN['en']).lower()}{d(2)}"]
            )
        case "selector.crypto_address":
            return rng.choice(CRYPTO)
        case "selector.domain":
            return rng.choice(
                ["example.com", "https://vk.com/id" + d(6), "www.shop-online.ru", "news.cn", "lemonde.fr"]
            )
        case "selector.mac_address":
            return ":".join(f"{rng.randrange(256):02x}" for _ in range(6))
        case "time.datetime":
            return _date(rng, start=2022, end=2024, style=date_style, with_time=True)
        case "time.date":
            return _date(rng, start=2022, end=2024, style=date_style)
        case "time.epoch":
            return str(rng.randint(1_600_000_000, 1_720_000_000))
        case "time.duration":
            return rng.choice([str(rng.randint(1, 3600)), f"00:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"])
        case "edge.amount":
            return rng.choice(
                [
                    f"{rng.uniform(1, 50000):.2f}",
                    f"{rng.randint(1, 900)} {rng.randint(100, 999)},{rng.randint(0, 99):02d}",
                ]
            )
        case "edge.currency":
            return rng.choice(["USD", "EUR", "RUB", "CNY", "руб.", "€"])
        case "edge.direction":
            return rng.choice(
                {"ru": ["вх", "исх", "входящий", "исходящий"], "zh": ["呼入", "呼出"]}.get(
                    lang, ["in", "out", "incoming", "outgoing"]
                )
            )
        case "key.row_id":
            return str(row + 1)
        case "key.reference":
            return f"TX{d(10)}"
        case "other.free_text":
            return rng.choice(
                {
                    "ru": [
                        "Позвонить после обеда, обсудить поставку оборудования на склад",
                        "Встреча перенесена на следующую неделю по просьбе клиента",
                    ],
                    "zh": ["请在下午给他回电话讨论设备交付到仓库的问题以及付款安排"],
                }.get(
                    lang,
                    [
                        "Call back after lunch to discuss the equipment delivery to the warehouse",
                        "Meeting moved to next week at the client's request",
                    ],
                )
            )
        case "other.boolean":
            return rng.choice(["true", "false", "1", "0", "yes", "no"])
        case "other.category":
            return rng.choice(["active", "blocked", "pending"])
    return ""


def _style_header(text: str, style: str) -> str:
    words = text.replace(".", " ").split()
    match style:
        case "snake":
            return "_".join(w.lower() for w in words)
        case "camel":
            return words[0].lower() + "".join(w[:1].upper() + w[1:] for w in words[1:]) if words else text
        case "upper":
            return text.upper()
    return text


def _role_header(base: str, role: str | None, *, lang: str) -> str:
    if not role:
        return base
    word = ROLE_WORDS[role][lang]
    return (
        f"{base} {word}" if lang in ("ru", "fr", "es", "ar") else f"{word}{base}" if lang == "zh" else f"{word} {base}"
    )


def make_table(name: str, directory: Path, *, rng: random.Random, rows: int = 400) -> SyntheticTable:
    """One messy table of scenario `name`, written to `directory` (csv, tsv, xlsx-free formats only)."""
    lang = rng.choice(list(GIVEN))
    columns = list(SCENARIOS[name])
    rng.shuffle(columns)
    if rng.random() < 0.3:
        columns.append(rng.choice([("key.row_id", None), ("other.boolean", None), ("other.category", None)]))
    style = rng.choice(["plain", "plain", "snake", "camel", "upper", "none", "title_rows"])
    date_style = rng.choice([0, 1, 2, 3] + ([4] if lang == "zh" else []))
    headers = [
        _style_header(_role_header(rng.choice(HEADERS[f].get(lang) or HEADERS[f]["en"]), role, lang=lang), style)
        for f, role in columns
    ]
    null_rate = rng.choice([0.0, 0.05, 0.2])
    body = [
        [
            ""
            if rng.random() < null_rate and f != "key.row_id"
            else value_for(f, lang=lang, rng=rng, row=i, date_style=date_style)
            for f, _ in columns
        ]
        for i in range(rows)
    ]
    fmt = rng.choice(["csv", "csv", "tsv", "semicolon", "jsonl"])
    path = (
        directory
        / f"{name}_{lang}_{style}_{rng.randrange(10**6):06d}.{ {'tsv': 'tsv', 'jsonl': 'jsonl'}.get(fmt, 'csv') }"
    )
    if fmt == "jsonl":
        with path.open("w", encoding="utf-8") as handle:
            for row in body:
                handle.write(json.dumps(dict(zip(_dedupe(headers), row, strict=True)), ensure_ascii=False) + "\n")
    else:
        delimiter = {"tsv": "\t", "semicolon": ";"}.get(fmt, ",")
        encoding = "cp1251" if lang == "ru" and rng.random() < 0.3 else "utf-8"
        with path.open("w", encoding=encoding, errors="replace", newline="") as handle:
            writer = csv.writer(handle, delimiter=delimiter)
            if style == "title_rows":
                writer.writerow([f"Export {datetime(2024, 3, 1):%Y-%m-%d}"])
                writer.writerow([])
            if style != "none":
                writer.writerows([headers])
            writer.writerows(body)
    return SyntheticTable(name=name, path=path, labels=[f for f, _ in columns], roles=[r for _, r in columns])


def _dedupe(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for h in headers:
        seen[h] = seen.get(h, 0) + 1
        out.append(h if seen[h] == 1 else f"{h}_{seen[h]}")
    return out


def make_tables(directory: Path, *, count: int = 42, seed: int = 7, rows: int = 400) -> list[SyntheticTable]:
    """`count` tables cycling through every scenario."""
    directory.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    names = list(SCENARIOS)
    return [make_table(names[i % len(names)], directory, rng=rng, rows=rows) for i in range(count)]
