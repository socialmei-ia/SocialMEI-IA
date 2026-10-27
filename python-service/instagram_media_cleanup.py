"""Delete expired Instagram staging media only; never touches posts or messages.
Run inside the team API container, without copying database credentials.
"""
import argparse
from database import connect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with connect() as conn:
        if args.apply:
            count = conn.execute('DELETE FROM socialmei.ig_meta_media WHERE expires_at<=NOW()').rowcount
        else:
            count = conn.execute('SELECT count(*) FROM socialmei.ig_meta_media WHERE expires_at<=NOW()').fetchone()[0]
    print(('Expired media removed: ' if args.apply else 'Expired media eligible: ') + str(count))


if __name__ == '__main__':
    main()
