import os
import shutil
from datetime import datetime


class DocFilesInfo(object):

    def __init__(self, xml_filename, report_path, wrk_path):
        self.xml_filename = xml_filename
        self.xml_path = os.path.dirname(xml_filename)

        xml_file = os.path.basename(xml_filename)
        self.xml_name = xml_file.replace('.sgm.xml', '').replace('.xml', '')
        self.new_name = self.xml_name

        self.xml_wrk_path = wrk_path + '/' + self.xml_name

        self.dtd_report_filename = report_path + '/' + self.xml_name + '.dtd.txt'
        self.style_report_filename = report_path + '/' + self.xml_name + '.rep.html'

        self.pmc_dtd_report_filename = report_path + '/' + self.xml_name + '.pmc.dtd.txt'
        self.pmc_style_report_filename = report_path + '/' + self.xml_name + '.pmc.rep.html'

        self.err_filename = report_path + '/' + self.xml_name + '.err.txt'
        self.html_filename = self.xml_wrk_path + '/' + self.xml_name + '.temp.htm'
        if not os.path.isfile(self.html_filename):
            self.html_filename += 'l'

        self.is_sgmxml = xml_filename.endswith('.sgm.xml')
        self.ctrl_filename = self.xml_wrk_path + '/' + self.xml_name + '.ctrl.txt' if self.is_sgmxml else None

    def clean(self):
        #clean_folder(self.xml_wrk_path)
        delete_files([self.err_filename, self.dtd_report_filename, self.style_report_filename, self.pmc_dtd_report_filename, self.pmc_style_report_filename, self.ctrl_filename])


def clean_folder(path):
    if os.path.isdir(path):
        for f in os.listdir(path):
            if os.path.isfile(path + '/' + f):
                os.unlink(path + '/' + f)
    else:
        os.makedirs(path)


def delete_files(files):
    for f in files:
        if f is not None:
            if os.path.isfile(f):
                os.unlink(f)


class Ahead(object):

    def __init__(self, record, ahead_db_name):
        self.record = record
        self.ahead_db_name = ahead_db_name

    @property
    def doi(self):
        return self.record.get('237')

    @property
    def filename(self):
        return self.record.get('2')

    @property
    def order(self):
        return self.record.get('121')


class AheadManager(object):

    def __init__(self, dao, journal_files):
        self.journal_files = journal_files
        self.dao = dao
        self.load()
        self.deleted = {}

    def prepare_ahead_id_files(self):
        for db_filename in self.journal_files.ahead_bases:
            name = os.basename(db_filename)[0:4]
            id_path = self.journal_files.ahead_id_path(name)
            if not os.path.isdir(id_path):
                os.makedirs(id_path)
            if os.listdir(id_path) == 0:
                #self.journal_files.create_ahead_id_files(name)
                records = self.dao.get_records(db_filename)
                previous = ''
                order = '00000'
                r = []
                for rec in records:
                    if rec.get('706') == 'i':
                        self.dao.save_id(id_path + '/i.id', [rec])
                    else:
                        current = rec.get('2')
                        if rec.get('706') == 'h':
                            order = '00000' + rec.get('121')
                            order = order[-5:]
                        if previous != current:
                            if len(r) > 0:
                                self.dao.save_id(id_path + '/' + order + '.id', r)
                                r = []
                            previous = current
                        r.append(rec)
                if len(r) > 0:
                    self.dao.save_id(id_path + '/' + order + '.id', r)

    def load(self):
        self.ahead_doi = {}
        self.ahead_filename = {}
        self.ahead_list = []
        for db_filename in self.journal_files.ahead_bases:
            h_records = self.h_records(db_filename)
            for h_record in h_records:
                ahead = Ahead(h_record, os.path.basename(db_filename))
                self.ahead_doi[ahead.doi] = len(self.ahead_list)
                self.ahead_filename[ahead.filename] = len(self.ahead_list)
                self.ahead_list.append(ahead)

    def h_records(self, db_filename):
        return self._select_h(self.dao.get_records(db_filename))

    def _select_h(self, records):
        return [rec for rec in records if rec.get('706') == 'h']

    def name(self, db_filename):
        return os.path.basename(db_filename)

    def find_ahead_data(self, doi, filename):
        data = None
        i = self.ahead_doi.get(doi, None)
        if i is None:
            i = self.ahead_filename.get(filename, None)
        if i is not None:
            data = self.ahead_list[i]
        return data

    def mark_ahead_as_deleted(self, ahead):
        """
        Mark as deleted
        """
        if not ahead.ahead_db_name is self.deleted.keys():
            self.deleted[ahead.ahead_db_name] = []
        self.deleted[ahead.ahead_db_name].append(ahead)

    def manage_ex_ahead_files(self, ahead):
        msg = []
        msg.append('Exclude ahead files of ' + ahead.filename)
        year = ahead.ahead_db_name[0:4]

        ex_ahead_markup_path, ex_ahead_body_path, ex_ahead_base_path = self.journal_files.ex_ahead_paths(year)
        for path in [ex_ahead_markup_path, ex_ahead_body_path, ex_ahead_base_path]:
            if not os.path.isdir(path):
                os.makedirs(path)

        # move files to ex-ahead folder
        xml_file, markup_file, body_file = self.journal_files.ahead_xml_markup_body(year, ahead.filename)
        if os.path.isfile(markup_file):
            shutil.move(markup_file, ex_ahead_markup_path)
            msg.append('move ' + markup_file + ' to ' + ex_ahead_markup_path)
        if os.path.isfile(body_file):
            shutil.move(body_file, ex_ahead_body_path)
            msg.append('move ' + body_file + ' to ' + ex_ahead_body_path)
        if os.path.isfile(xml_file):
            shutil.move(xml_file, ex_ahead_markup_path)
            msg.append('move ' + xml_file + ' to ' + ex_ahead_markup_path)
        if os.path.isfile(self.journal_files.ahead_id_filename(year, ahead.order)):
            os.unlink(self.journal_files.ahead_id_filename(year, ahead.order))
            msg.append('delete ' + self.journal_files.ahead_id_filename(year, ahead.order))
        return '\n'.join(msg)

    def save_ex_ahead_record(self, ahead):
        self.dao.append_records([ahead.record], self.journal_files.ahead_base('ex-' + ahead.ahead_db_name[0:4]))

    def manage_ex_ahead(self, doi, filename):
        """
        Exclude ISIS record of ahead database (serial)
        """
        msg = ''
        ahead = self.find_ahead_data(doi, filename)
        if ahead is not None:
            self.mark_ahead_as_deleted(ahead)
            msg = self.manage_ex_ahead_files(ahead)
            self.save_ex_ahead_record(ahead)
        return (ahead, msg)

    def finish_manage_ex_ahead(self):
        loaded = []
        for ahead_db_name, ahead_list in self.deleted.items():
            id_path = self.journal_files.ahead_id_path(ahead_db_name[0:4])
            base = self.journal_files.ahead_base(ahead_db_name[0:4])
            if os.path.isfile(id_path + '/i.id'):
                self.dao.save_id_records(id_path + '/i.id', base)
            for f in os.listdir(id_path):
                if f.endswith('.id') and f != '00000.id' and f != 'i.id':
                    self.dao.append_id_records(id_path + '/' + f, base)
                    loaded.append(ahead_db_name + ' ' + f)
        return '\n'.join(loaded)


class ArticleFiles(object):

    def __init__(self, issue_files, order, xml_name):
        self.issue_files = issue_files
        self.order = order
        self.xml_name = xml_name

    @property
    def id_filename(self):
        return self.issue_files.id_path + self.order + '.id'

    @property
    def relative_xml_filename(self):
        return self.issue_files.relative_issue_path + '/' + self.xml_name + '.xml'


class IssueFiles(object):

    def __init__(self, journal_files, issue_folder, xml_path, web_path):
        self.journal_files = journal_files
        self.issue_folder = issue_folder
        self.xml_path = xml_path
        self.web_path = web_path

    @property
    def issue_path(self):
        return self.journal_files.journal_path + '/' + self.issue_folder

    @property
    def relative_issue_path(self):
        return self.journal_files.acron + '/' + self.issue_folder

    @property
    def id_path(self):
        return self.issue_path + '/id/'

    @property
    def id_filename(self):
        return self.issue_path + '/id/i.id'

    @property
    def base_path(self):
        return self.issue_path + '/base'

    @property
    def base_reports_path(self):
        return self.issue_path + '/base_reports'

    @property
    def base(self):
        return self.base_path + '/' + self.issue_folder

    def copy_files_to_web(self):
        msg = []
        path = {}
        path['pdf'] = self.web_path + '/bases/pdf/' + self.relative_issue_path
        path['html'] = self.web_path + '/htdocs/img/revistas/' + self.relative_issue_path + '/html/'
        path['xml'] = self.web_path + '/bases/xml/' + self.relative_issue_path
        path['img'] = self.web_path + '/htdocs/img/revistas/' + self.relative_issue_path
        for p in path.values():
            if not os.path.isdir(p):
                os.makedirs(p)
        for f in os.listdir(self.xml_path):
            if os.path.isfile(self.xml_path + '/' + f):
                ext = f[f.rfind('.'):]
                if path.get(ext) is not None:
                    shutil.copy(self.xml_path + '/' + f, path[ext])
                    msg.append('copying ' + self.xml_path + '/' + f + ' to ' + path[ext])
                else:
                    shutil.copy(self.xml_path + '/' + f, path['img'])
                    msg.append('copying ' + self.xml_path + '/' + f + ' to ' + path['img'])
        return '\n'.join(msg)

    def move_reports(self, report_path):
        if not self.base_reports_path == report_path:
            if not os.path.isdir(self.base_reports_path):
                os.makedirs(self.base_reports_path)
            for report_file in os.listdir(report_path):
                shutil.copy(report_path + '/' + report_file, self.base_reports_path)
                os.unlink(report_path + '/' + report_file)


class JournalFiles(object):

    def __init__(self, serial_path, acron):
        self.acron = acron
        self.journal_path = serial_path + '/' + acron
        self.years = [str(int(datetime.now().isoformat()[0:4])+1 - y) for y in range(0, 5)]

    def ahead_base(self, year):
        return self.journal_path + '/' + year + 'nahead' + '/base/' + year + 'nahead'

    def ahead_xml_markup_body(self, year, filename):
        m = self.journal_path + '/' + year + 'nahead' + '/markup/' + filename
        b = self.journal_path + '/' + year + 'nahead' + '/body/' + filename
        return (self.journal_path + '/' + year + 'nahead' + '/xml/' + filename, m, b)

    def ahead_id_filename(self, year, order):
        order = '00000' + order
        order = order[-5:]
        return self.journal_path + '/' + year + 'nahead' + '/id/' + order + '.id'

    def ahead_id_path(self, year):
        return self.journal_path + '/' + year + 'nahead' + '/id/'

    def ex_ahead_paths(self, year):
        path = self.journal_path + '/ex-' + year + 'nahead'
        m = path + '/markup/'
        b = path + '/body/'
        base = path + '/base/'
        return (m, b, base)

    @property
    def ahead_bases(self):
        bases = []
        for y in self.years:
            if os.path.isfile(self.ahead_base(y) + '.mst'):
                bases.append(self.ahead_base(y))
        return bases


class IssueDAO(object):

    def __init__(self, dao, db_filename):
        self.dao = dao
        self.db_filename = db_filename

    def expr(self, issue_id, pissn, eissn, acron=None):
        _expr = []
        if pissn is not None:
            _expr.append(pissn + issue_id)
        if eissn is not None:
            _expr.append(eissn + issue_id)
        if acron is not None:
            _expr.append(acron)
        r = ' OR '.join(_expr) if len(_expr) > 0 else None
        return r

    def search(self, issue_label, pissn, eissn):
        expr = self.expr(issue_label, pissn, eissn)
        return self.dao.get_records(self.db_filename, expr)


class ArticleDAO(object):

    def __init__(self, dao):
        self.dao = dao

    def create_id_file(self, i_record, article, section_code, article_files):
        if not os.path.isdir(article_files.issue_files.id_path):
            os.makedirs(article_files.issue_files.id_path)
        if not os.path.isdir(os.path.dirname(article_files.issue_files.base)):
            os.makedirs(os.path.dirname(article_files.issue_files.base))

        if article.order != '00000':
            from isis_models import ArticleRecords
            article_isis = ArticleRecords(article, i_record, section_code, article_files)
            self.dao.save_id(article_files.id_filename, article_isis.records)
        else:
            print('Invalid value for order.')
        return os.path.isfile(article_files.id_filename)

    def finish_conversion(self, issue_record, issue_files):
        loaded = []
        self.dao.save_records([issue_record], issue_files.base)
        for f in os.listdir(issue_files.id_path):
            if f.endswith('.id') and f != '00000.id' and f != 'i.id':
                self.dao.append_id_records(issue_files.id_path + '/' + f, issue_files.base)
                loaded.append(f)
        return loaded