"""
helper functions for encoding and obsfuscating user ids for disclaimers
Usage
encoded_id_for_url = int_str(chaffify(user_id))
user_id = dechaffify(str_int(encoded_id_for_url))

"""

def int_str(val, keyspace="59roepma2nvxb07fwliqt83_u6kgzs41-ycdjh"):
    """
    Turn a positive integer into a string. Each each character in keyspace
    must occur only once
    """
    assert val >= 0
    out = ""
    while val > 0:
        val, digit = divmod(val, len(keyspace))
        out += keyspace[digit]
    return out[::-1]


def str_int(val, keyspace="59roepma2nvxb07fwliqt83_u6kgzs41-ycdjh"):
    """ Turn a string into a positive integer. """
    out = 0
    for c in val:
        out = out * len(keyspace) + keyspace.index(c)
    return out


def chaffify(val, chaff_val=87953):
    """ Add chaff to the given positive integer. """
    return val * chaff_val


def dechaffify(chaffied_val, chaff_val=87953):
    """
    Dechaffs the given chaffed value. chaff_val must be the same as given to
    chaffify2(). If the value does not seem to be correctly chaffed, raises a
    ValueError. """
    val, chaff = divmod(chaffied_val, chaff_val)
    if chaff != 0:
        raise ValueError("Invalid chaff in value")
    return val
