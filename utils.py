
def hyphenate_citizen_id(unhyphenated_id: str) -> str:
    return (f"{unhyphenated_id[0]}-{unhyphenated_id[1:5]}-{unhyphenated_id[5:10]}" +
            f"-{unhyphenated_id[10:12]}-{unhyphenated_id[12]}")
