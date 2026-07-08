def main():
    load_dotenv()

    sites_path = os.getenv("SITES_JSON_PATH", "sites.json")
    sites = load_sites(sites_path)

    current_start, current_end, previous_start, previous_end = report_periods()

    service = build_gsc_service()

    results = collect_results(
        service,
        sites,
        current_start,
        current_end,
        previous_start,
        previous_end,
    )

    message = build_slack_message(
        results,
        current_start,
        current_end,
        previous_start,
        previous_end,
    )

    print(message)

    # Slack delivery is handled by Claude Routine through the Slack connector.
    # Do not post via Slack webhook from this script.


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
