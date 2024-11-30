import datetime
import requests
import re
import time
from bs4 import BeautifulSoup
from collections import defaultdict, namedtuple
from data import MAILING_DATES, GITHUB_ISSUE, ISO_CPP_PLENARIES, URLS, WG_ABREVIATIONS

PaperMailingEntry = namedtuple("PaperMailingEntry", ["number", "title", "revision", "target", "mailing"])
PaperRevision = namedtuple("PaperRevision", ["number", "target", "mailing"])
Paper = namedtuple("Paper", ["number", "title", "revisions", "plenary_approved"])


def date_latest_plenary():
    return [plenary_date for plenary_date in sorted(ISO_CPP_PLENARIES.keys()) if plenary_date < datetime.date.today()][-1]

def mailings_since_last_plenary():
    return [mailing for mailing, mailing_date in MAILING_DATES.items() if mailing_date < datetime.date.today() and mailing_date > date_latest_plenary()]

def extract_target_groups(target_groups_text):
    for target in target_groups_text.split(','):
        stripped_target = target.strip()
        if stripped_target in WG_ABREVIATIONS:
            yield WG_ABREVIATIONS[stripped_target]
        else:
            print(f'Unrecognized target group: {stripped_target}')
            raise RuntimeError

def get_github_issues_with_plenary_approved():
    plenary_approved_issues = set()
    url_to_load = "https://api.github.com/repos/cplusplus/papers/issues?state=all&labels=plenary-approved"
    while url_to_load:
        response = requests.get(url_to_load)
        data = response.json()
        for element in data:
            if element['number']:
                plenary_approved_issues.add(element['number'])
        next = response.links.get('next')
        url_to_load = next['url'] if next else None
    return plenary_approved_issues

def is_plenary_approved(paper_number, plenary_aproved_github_issues):
    github_issue_number = GITHUB_ISSUE.get(paper_number)
    if github_issue_number:
        return github_issue_number in plenary_approved_github_issues
    # Give some time between requests
    time.sleep(0.05)
    response = requests.get(f'https://wg21.link/{paper_number}/github')
    match = re.search(r"issues/(\d+)", response.url)
    if match:
        github_issue_number = match.group(1)
        return github_issue_number in plenary_aproved_github_issues
    else:
        print(f"No issue found for paper {paper_number}: {response.status_code} {response.url}")
        return False

def create_paper_from_table_entry(potential_paper_row):
    paper_columns = potential_paper_row.find_all("td")
    if not paper_columns:
        return None
    match = re.search(r"(P\d+)(R\d+)", paper_columns[0].text.strip())
    if not match:
        return None
    paper_number = match.group(1)
    paper_revision = match.group(2)
    paper_title = paper_columns[1].text.strip()
    paper_mailing = paper_columns[4].text.strip()
    paper_target = extract_target_groups(paper_columns[6].text.strip())
    return PaperMailingEntry(number=paper_number, title=paper_title, revision=paper_revision, target=paper_target, mailing=paper_mailing)

def combined_revisions_for_printing(paper_revisions):
    if not paper_revisions:
        return []
    CombinedRevision = namedtuple('CombinedRevision', ['revisions', 'target', 'mailings'])
    combined_revisions = [CombinedRevision(revisions=[paper_revisions[0].number], target=paper_revisions[0].target, mailings=[paper_revisions[0].mailing])]
    for paper_revision in paper_revisions[1:]:
        if paper_revision.target == combined_revisions[-1].target:
            combined_revisions[-1].revisions.append(paper_revision.number)
            combined_revisions[-1].mailings.append(paper_revision.mailing)
        else:
            combined_revisions.append(CombinedRevision(revisions=[paper_revision.number], target=paper_revision.target, mailings=[paper_revision.mailing]))
    return combined_revisions

def print_paper(paper, new_mailings):
    new_paper = False
    combined_revisions = combined_revisions_for_printing(paper.revisions)
    for combined_revision in combined_revisions:
        if 'R0' in combined_revision.revisions and combined_revision.mailings[combined_revision.revisions.index('R0')] in new_mailings:
            new_paper = True
    new_text = ' **(NEW)**' if new_paper else ''
    approved_text = ' **(APPROVED)**' if paper.plenary_approved else ''
    print(f"- [{paper.number}](https://wg21.link/{paper.number}/github) {paper.title}{new_text}{approved_text}")
    for combined_revision in combined_revisions:
        revisions_with_links = [f"[{revision}](https://wg21.link/{paper.number}{revision})" for revision in combined_revision.revisions]
        print(f"  - {", ".join(revisions_with_links)} for {", ".join(combined_revision.target)} in {", ".join(combined_revision.mailings)}")

def aggregate_paper_mailing_entries(paper_mailing_entries, plenary_approved_github_issues):
    papers = dict()
    papers_mailing_entries_processed = 0
    for paper_mailing_entry in paper_mailing_entries:
        paper_revision = PaperRevision(
            number=paper_mailing_entry.revision,
            target=paper_mailing_entry.target,
            mailing=paper_mailing_entry.mailing
        )
        if paper_mailing_entry.number in papers:
            papers[paper_mailing_entry.number].revisions.append(paper_revision)
        else:
            papers[paper_mailing_entry.number] = Paper(
                number=paper_mailing_entry.number,
                title=paper_mailing_entry.title,
                revisions=[paper_revision],
                plenary_approved=is_plenary_approved(paper_mailing_entry.number, plenary_approved_github_issues)
            )
        papers_mailing_entries_processed += 1
        if papers_mailing_entries_processed % 50 == 0:
            print(f"Processed {papers_mailing_entries_processed} mailing entries resulting in {len(papers)} papers")
    return papers.values()

def collect_paper_mailing_entries(urls):
    for url in urls:
        page = requests.get(url)
        soup = BeautifulSoup(page.content, "html.parser")

        potential_paper_rows = soup.find_all("tr")
        for potential_paper_row in potential_paper_rows:
            paper_mailing_entry = create_paper_from_table_entry(potential_paper_row)
            if paper_mailing_entry:
                yield paper_mailing_entry

if __name__ == '__main__':
    new_mailings = mailings_since_last_plenary()
    plenary_approved_github_issues = get_github_issues_with_plenary_approved()

    papers = aggregate_paper_mailing_entries(collect_paper_mailing_entries(URLS), plenary_approved_github_issues)
    papers_per_target = defaultdict(list)
    updated_papers = []
    for paper in papers:
        new_paper = False
        for paper_revision in paper.revisions:
            if paper_revision.mailing in new_mailings:
                new_paper = True
                for target in paper_revision.target:
                    if paper not in papers_per_target[target]:
                        papers_per_target[target].append(paper)
        if new_paper:
            updated_papers.append(paper)

    print("# Paper update report since last plenary")
    print("")
    print("## About this report")
    print("")
    print("This is an alternative format of the content available in https://www.open-std.org/jtc1/sc22/wg21/docs/papers/202X/.")
    print("For each paper that has an update since last plenary meeting, all known revisions are printed with the different target groups.")
    print("The paper contains the label **(NEW)** if no version of the paper was existing before the previous plenary.")
    print("")

    for target, papers in papers_per_target.items():
        if papers:
            print(f"## Papers updated targeting {target}")
            print("")
            for paper in papers:
                print_paper(paper, new_mailings)
            print("")

    print("## All papers updated")
    print("")
    for paper in updated_papers:
        print_paper(paper, new_mailings)
