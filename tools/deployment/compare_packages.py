"""Compare ZIP inventories without extraction or reading configuration values."""
import argparse
import json
import zipfile


def inventory(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError('El ZIP contiene entradas duplicadas')
        return {entry.filename: (entry.CRC, entry.file_size) for entry in archive.infolist() if not entry.is_dir()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original')
    parser.add_argument('revised')
    args = parser.parse_args()
    original, revised = inventory(args.original), inventory(args.revised)
    print(json.dumps({
        'added': sorted(revised.keys() - original.keys()),
        'removed': sorted(original.keys() - revised.keys()),
        'changed': sorted(name for name in original.keys() & revised.keys() if original[name] != revised[name]),
        'method': 'ZIP CRC32 and size; inventory comparison, not a security certification',
    }, indent=2))


if __name__ == '__main__':
    main()
