# code = utf-8

import os
import webbrowser
import shutil

from __init__ import _
from . import attributes
from . import article
from . import article_reports
from . import article_validations
from . import article_utils
from . import fs_utils
from . import html_reports
from . import validation_status
from . import xpchecker
from . import utils


class PackageValidationsResult(dict):

    def __init__(self):
        dict.__init__(self)
        self.title = ''

    @property
    def total(self):
        return sum([item.total() for item in self.values()])

    @property
    def fatal_errors(self):
        return sum([item.fatal_errors for item in self.values()])

    @property
    def errors(self):
        return sum([item.errors for item in self.values()])

    @property
    def warnings(self):
        return sum([item.warnings for item in self.values()])

    def report(self, errors_only=False):
        _reports = ''
        for xml_name in sorted(self.keys()):
            results = self[xml_name]
            if results.total() > 0 or errors_only is False:
                _reports += html_reports.tag('h4', xml_name)
                _reports += results.message
        if len(_reports) > 0:
            _reports = self.title + _reports
        return _reports


class ValidationsResult(object):

    def __init__(self):
        self._message = ''
        self.numbers = {}

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, value):
        self._message = value
        self.calculate_numbers()

    def calculate_numbers(self):
        for status, style_checker_error_type in zip(validation_status.STATUS_LEVEL_ORDER, validation_status.STYLE_CHECKER_ERROR_TYPES):
            self.numbers[status] = word_counter(self.message, status)
            if len(style_checker_error_type) != '':
                self.numbers[status] += number_after_words(self.message, style_checker_error_type)

    def total(self):
        return sum([item for item in self.numbers.values()])

    @property
    def statistics_label_and_number(self):
        items = []
        for status in validation_status.STATUS_LEVEL_ORDER:
            items.append((validation_status.STATUS_LABELS.get(status), str(self.numbers.get(status, 0))))
        return items

    @property
    def fatal_errors(self):
        return self.numbers.get(validation_status.STATUS_FATAL_ERROR, 0)

    @property
    def errors(self):
        return self.numbers.get(validation_status.STATUS_ERROR, 0)

    @property
    def blocking_errors(self):
        return self.numbers.get(validation_status.STATUS_BLOCKING_ERROR, 0)

    @property
    def warnings(self):
        return self.numbers.get(validation_status.STATUS_WARNING, 0)

    def statistics_display(self, inline=True):
        tag_name = 'span'
        text = ' | '.join([k + ': ' + v for k, v in self.statistics_label_and_number if v != '0'])
        if not inline:
            tag_name = 'div'
            text = ''.join([html_reports.tag('p', html_reports.display_label_value(_('Total of ') + k, v)) for k, v in self.statistics_label_and_number])
        style = validation_status.message_style(self.statistics_label_and_number)
        r = html_reports.tag(tag_name, text, style)
        return r


class ValidationsFile(ValidationsResult):

    def __init__(self, filename):
        ValidationsResult.__init__(self)
        self.filename = filename
        self._read()

    @ValidationsResult.message.setter
    def message(self, _message):
        self._message = _message
        self.calculate_numbers()
        self._write()

    def _write(self):
        m = self.message if self.message is not None else ''
        fs_utils.write_file(self.filename, m)

    def _read(self):
        if os.path.isfile(self.filename):
            self._message = fs_utils.read_file(self.filename)
        else:
            self._message = ''


class XMLJournalDataValidator(object):

    def __init__(self, journal_data):
        self.journal_data = journal_data

    def validate(self, article):
        if self.journal_data is None:
            r = validation_status.STATUS_BLOCKING_ERROR + ': ' + _('Unable to identify {unidentified}. ').format(unidentified=_('journal'))
        else:
            items = []
            license_url = None
            if len(article.article_licenses) > 0:
                license_url = article.article_licenses.values()[0].get('href')
            items.append([_('NLM title'), article.journal_id_nlm_ta, self.journal_data.nlm_title, validation_status.STATUS_FATAL_ERROR])
            items.append([_('journal-id (publisher-id)'), article.journal_id_publisher_id, self.journal_data.acron, validation_status.STATUS_FATAL_ERROR])
            items.append([_('e-ISSN'), article.e_issn, self.journal_data.e_issn, validation_status.STATUS_FATAL_ERROR])
            items.append([_('print ISSN'), article.print_issn, self.journal_data.p_issn, validation_status.STATUS_FATAL_ERROR])
            items.append([_('publisher name'), article.publisher_name, self.journal_data.publisher_name, validation_status.STATUS_ERROR])
            items.append([_('license'), license_url, self.journal_data.license, validation_status.STATUS_ERROR])
            r = evaluate_journal_data(items)
        return r


class XMLIssueDataValidator(object):

    def __init__(self, is_db_generation, issue_error_msg, issue_models):
        self.issue_error_msg = issue_error_msg
        self.issue_models = issue_models
        self.is_db_generation = is_db_generation

    def validate(self, article):
        r = ''
        if self.is_db_generation:
            r = validation_status.STATUS_BLOCKING_ERROR + ': ' + _('Unable to identify {unidentified}. ').format(unidentified=_('issue'))
            if self.issue_error_msg is not None:
                r += self.issue_error_msg
            if self.issue_models:
                r = self.issue_models.validate_article_issue_data(article)
        return r


class XMLStructureValidator(object):

    def __init__(self, dtd_files):
        self.dtd_files = dtd_files

    def validate(self, work_area):
        separator = '\n\n\n' + '.........\n\n\n'

        name_error = ''
        if '_' in work_area.xml_name or '.' in work_area.xml_name:
            name_error = rst_title(_('Name errors')) + _('{value} has forbidden characters, which are {forbidden_characters}').format(value=work_area.xml_name, forbidden_characters='_.') + separator

        files_errors = ''
        if os.path.isfile(work_area.err_filename):
            files_errors = fs_utils.read_file(work_area.err_filename)

        for f in [work_area.dtd_report_filename, work_area.style_report_filename, work_area.data_report_filename, work_area.pmc_style_report_filename]:
            if os.path.isfile(f):
                os.unlink(f)
        xml_filename = work_area.new_xml_filename

        xml, valid_dtd, valid_style = xpchecker.validate_article_xml(xml_filename, self.dtd_files, work_area.dtd_report_filename, work_area.style_report_filename)
        xml_f, xml_e, xml_w = valid_style

        xml_structure_report_content = ''
        if os.path.isfile(work_area.dtd_report_filename):
            xml_structure_report_content = rst_title(_('DTD errors')) + fs_utils.read_file(work_area.dtd_report_filename)
            #os.unlink(work_area.dtd_report_filename)

        report_content = ''
        if xml is None:
            xml_f += 1
            report_content += validation_status.STATUS_FATAL_ERROR + ' ' + _('XML file is invalid') + '\n'
        if not valid_dtd:
            xml_f += 1
            report_content += validation_status.STATUS_FATAL_ERROR + ' ' + _('XML file has DTD errors') + '\n'
        if len(name_error) > 0:
            xml_f += 1
            report_content += validation_status.STATUS_FATAL_ERROR + ' ' + _('XML file has name errors') + '\n'

        if len(report_content) > 0:
            report_content = rst_title(_('Summary')) + report_content + separator
            report_content = report_content.replace('\n', '<br/>')

        if xml_f > 0:
            fs_utils.append_file(work_area.err_filename, name_error + xml_structure_report_content)

        if work_area.ctrl_filename is None:
            if xml_f + xml_e + xml_w == 0:
                os.unlink(work_area.style_report_filename)
        else:
            fs_utils.write_file(work_area.ctrl_filename, 'Finished')

        for rep_file in [work_area.err_filename, work_area.style_report_filename]:
            if os.path.isfile(rep_file):
                report_content += extract_report_core(fs_utils.read_file(rep_file))
        return report_content


class XMLContentValidator(object):

    def __init__(self, doi_services, articles_data):
        self.articles_data = articles_data
        self.doi_services = doi_services

    def validate(self, article, pkg_path, work_area, is_xml_generation):
        article_display_report = None
        article_validation_report = None
        article_validation = None

        if article.tree is None:
            content = validation_status.STATUS_BLOCKING_ERROR + ': ' + _('Unable to get data from {item}.').format(item=work_area.new_name)
        else:
            article_validation = article_validations.ArticleContentValidation(self.doi_services, self.articles_data.journal, article, (self.articles_data.articles_db_manager is not None), False)
            article_display_report = article_reports.ArticleDisplayReport(article_validation, pkg_path, work_area.new_name)
            article_validation_report = article_reports.ArticleValidationReport(article_validation)

            content = []

            if is_xml_generation:
                content.append(article_display_report.issue_header)
                content.append(article_display_report.article_front)

                content.append(article_validation_report.validations(display_all_message_types=False))
                content.append(article_display_report.table_tables)

                content.append(article_display_report.article_body)
                content.append(article_display_report.article_back)

            else:
                content.append(article_validation_report.validations(display_all_message_types=False))
                content.append(article_display_report.table_tables)
                content.append(article_display_report.files_and_href())

            content = html_reports.join_texts(content)
        return content, article_display_report


class ArticleValidations(object):

    def __init__(self, work_area, is_xml_generation, is_db_generation):
        self.work_area = work_area
        self.is_xml_generation = is_xml_generation
        self.is_db_generation = is_db_generation
        self.validations_file = {}
        self.validations_file['journal'] = ValidationsFile(self.work_area.journal_validations_filename)
        self.validations_file['issue'] = ValidationsFile(self.work_area.issue_validations_filename)
        self.validations_file['xmlstructure'] = ValidationsFile(self.work_area.err_filename_html)
        self.validations_file['xmlcontent'] = ValidationsFile(self.work_area.data_report_filename)

    @property
    def journal_validation(self):
        return self.validations_file['journal'].message

    @property
    def issue_validation(self):
        return self.validations_file['issue'].message

    @property
    def xmlcontent_validation(self):
        return self.validations_file['xmlcontent'].message

    @property
    def xmlstructure_validation(self):
        return self.validations_file['xmlstructure'].message

    @journal_validation.setter
    def journal_validation(self, validation_result):
        self.validations_file['journal'].message = validation_result

    @issue_validation.setter
    def issue_validation(self, validation_result):
        self.validations_file['issue'].message = validation_result

    @xmlstructure_validation.setter
    def xmlstructure_validation(self, validation_result):
        self.validations_file['xmlstructure'].message = validation_result

    @xmlcontent_validation.setter
    def xmlcontent_validation(self, validation_result):
        self.validations_file['xmlcontent'].message = validation_result
        if self.is_xml_generation:
            stats = self.validations_file['xmlcontent'].statistics_display(False)
            title = [_('Data Quality Control'), self.work_area.new_name]
            self.validations_file['xmlcontent'].message = html_reports.report_title(title) + stats + self.validations_file['xmlcontent'].message

    @property
    def fatal_errors(self):
        return sum([item.fatal_errors for item in self.validations_file.values()])

    def hide_and_show_block(self, report_id):
        blocks = []
        block_parent_id = report_id + self.work_area.new_name
        blocks.append((_('Structure Validations'), 'xmlrep', self.validations_file['xmlstructure']))
        blocks.append((_('Contents Validations'),  'datarep', self.validations_file['xmlcontent']))
        if self.is_db_generation:
            blocks.append((_('Converter Validations'), 'xcrep', self.validations_file['issue']))
        _blocks = []
        for label, style, validations_file in blocks:
            if validations_file.total() > 0:
                status = validations_file.statistics_display()
                _blocks.append(html_reports.HideAndShowBlockItem(block_parent_id, label, style + self.work_area.new_name, style, validations_file.message, status))
        return html_reports.HideAndShowBlock(block_parent_id, _blocks)


class ArticlesPackage(object):

    def __init__(self, pkg_path, pkg_articles, is_xml_generation):
        self.pkg_path = pkg_path
        self.pkg_articles = pkg_articles
        self.is_xml_generation = is_xml_generation
        self.xml_names = [name for name in os.listdir(self.pkg_path) if name.endswith('.xml')]

    @property
    def xml_list(self):
        r = ''
        r += '<p>' + _('XML path') + ': ' + self.pkg_path + '</p>'
        r += '<p>' + _('Total of XML files') + ': ' + str(len(self.xml_names)) + '</p>'
        r += html_reports.format_list('', 'ol', self.xml_names)
        r = '<div class="xmllist">' + r + '</div>'
        return r


class ArticlesData(object):

    def __init__(self):
        self.articles_db_manager = None
        self.journal = None
        self.journal_data = None
        self.acron_issue_label = None
        self.issue_models = None
        self.issue_error_msg = None
        self.issue_files = None

    def setup(self, pkg, journals_manager, db_manager):
        self._identify_journal_data(pkg.pkg_articles, journals_manager)
        if db_manager is not None:
            self._identify_issue_data(db_manager)
            self._identify_articles_data(pkg.pkg_path, db_manager)

    def _identify_journal_data(self, pkg_articles, journals_manager):
        #journals_manager = xc_models.JournalsManager()
        journals = [(a.journal_title, a.print_issn, a.e_issn, a.issue_label) for a in pkg_articles.values() if a.journal_title is not None and a.issue_label is not None and (a.print_issn is not None or a.e_issn is not None)]
        journals = list(set(journals))
        if len(journals) > 0:
            journal = article.Journal()
            if len(journals[0]) == 4:
                journal.journal_title, journal.p_issn, journal.e_issn, self.issue_label = journals[0]
                self.journal, self.journal_data = journals_manager.journal(journal.p_issn, journal.e_issn, journal.journal_title)

    def _identify_issue_data(self, db_manager):
        if db_manager is not None and self.journal is not None:
            self.acron_issue_label, self.issue_models, self.issue_error_msg = db_manager._identify_issue_models(self.journal.journal_title, self.issue_label, self.journal.p_issn, self.journal.e_issn)

    def _identify_articles_data(self, pkg_path, db_manager):
        if self.issue_error_msg is None:
            self.issue_files = db_manager.get_issue_files(self.issue_models, pkg_path)
            self.articles_db_manager = xc_models.ArticlesDBManager(db_manager.db_isis, self.issue_files)


class OrderValidations(object):

    def __init__(self, registered_articles, pkg_articles):
        self.registered_articles = registered_articles
        self.pkg_articles = pkg_articles

    def report_content(self):
        self.check_order_changes_requested()
        self.evaluate_new_article_names()
        return self.validate_resulting_orders_report()

    @property
    def marked_to_delete(self):
        return {a.order: k for k, a in self.pkg_articles.items() if a.marked_to_delete}

    @property
    def registered_orders(self):
        return {a.order: k for k, a in self.registered_articles.items()}

    def check_order_changes_requested(self):
        self.valid_orders_change_request = {}
        self.invalid_orders_change_request = {}
        for name, article in self.pkg_articles.items():
            if name in self.registered_articles.keys():
                if self.registered_articles[name].order != article.order:
                    exact_comparison_result, relaxed_comparison_result = self._check_title_and_authors_changes(self.registered_articles[name], article)
                    allowed_to_update, status, message = self._evaluate_comparison_results(exact_comparison_result, relaxed_comparison_result)
                    if allowed_to_update:
                        self.valid_orders_change_request[name] = (self.registered_articles[name].order, article.order)
                    else:
                        self.invalid_orders_change_request[name] = (status, message)

    def _check_title_and_authors_changes(self, registered, article):
        labels = [_('titles'), _('authors')]
        validations = []
        validations.append((registered.textual_titles, article.textual_titles))
        validations.append((registered.textual_contrib_surnames, article.textual_contrib_surnames))
        exact_comparison_result = [(label, items) for label, items in zip(labels, validations) if not items[0] == items[1]]
        relaxed_comparison_result = [(label, items) for label, items in zip(labels, validations) if not utils.is_similar(items[0], items[1])]
        return (exact_comparison_result, relaxed_comparison_result)

    def _evaluate_comparison_results(self, exact_comparison_result, relaxed_comparison_result):
        allowed_to_update = False
        status = validation_status.STATUS_BLOCKING_ERROR
        message = ''
        if len(exact_comparison_result) == 0:
            # no changes
            allowed_to_update = True
            status = validation_status.STATUS_INFO
        elif len(relaxed_comparison_result) == 0:
            # acceptable changes
            allowed_to_update = True
            status = validation_status.STATUS_WARNING
        message = self._differences_message(status, exact_comparison_result)
        return (allowed_to_update, status, message)

    @property
    def _differences_message(self, status, comparison_result):
        msg = []
        if len(comparison_result) > 0:
            for label, differences in comparison_result:
                msg.append(html_reports.p_message(status))
                msg.append(html_reports.tag('h5', label))
                msg.append(html_reports.display_label_value(_('registered'), differences[0]))
                msg.append(html_reports.display_label_value(_('in the package'), differences[1]))
        return ''.join(msg)

    def evaluate_new_article_names(self):
        self.valid_name_change_request = {}
        self.invalid_name_change_request = {}
        self.requested_new_order = {}
        for name, article in self.pkg_articles.items():
            if not name in self.registered_articles.keys():
                if article.order in self.registered_orders.keys():
                    # test if only filename has changed
                    exact_comparison_result, relaxed_comparison_result = self._check_title_and_authors_changes(self.registered_articles[name], article)
                    allowed_to_update, status, message = self._evaluate_comparison_results(exact_comparison_result, relaxed_comparison_result)
                    if allowed_to_update:
                        self.valid_name_change_request[name] = self.registered_orders[order]
                    else:
                        self.invalid_name_change_request[name] = (status, message)
                else:
                    self.requested_new_order[name] = article.order

    @property
    def resulting_orders(self):
        messages = []
        # registered
        orders = {a.order: [name] for name, a in self.registered_articles.items()}
        orders_history = {a.order: [html_reports.tag('p', _('registered'))] for name, a in self.registered_articles.items()}
        # marked to delete
        for order, name in self.marked_to_delete.items():
            if orders.get(order) is not None:
                if name in orders[order]:
                    orders[order].remove(name)
                    orders_history[order].append(html_reports.tag('p', _('mark to exclude')))
                else:
                    orders_history[order].append(html_reports.tag('p', _('not found to exclude')))
        # name changed
        #self.valid_name_change_request = {}
        for new_name, previous_name in self.valid_name_change_request.items():
            orders_history[self.registered_articles[previous_name].order].append(html_reports.tag('p', _('filename changed: {previous} to {current}').format(previous=previous_name, current=new_name)))
        #self.invalid_name_change_request = {}
        for new_name, data in self.invalid_name_change_request.items():
            status, message = data
            orders_history[self.pkg_articles[new_name].order].append(html_reports.p_message(status) + html_reports.tag('p', _('Unable to change filename: {previous} to {current}. ').format(previous=self.registered_orders[self.pkg_articles[new_name].order], current=new_name)) + html_reports.tag('p', message))
        # order changed
        # self.valid_orders_change_request = {}
        for name, order_changes in self.valid_orders_change_request.items():
            previous_order, new_order = order_changes
            if name in orders[previous_order]:
                orders[previous_order].remove(name)
                orders_history[previous_order].append(html_reports.tag('p', _('mark to exclude')))
            else:
                orders_history[previous_order].append(html_reports.tag('p', _('not found to exclude')))
            if not new_order in orders.keys():
                orders[new_order] = []
            orders_history[previous_order].append(html_reports.tag('p', _('order changed: {previous} to {current}').format(previous=previous_order, current=new_order)))
            orders[new_order].append(name)
            orders_history[new_order].append(html_reports.tag('p', _('order changed: {previous} to {current}').format(previous=previous_order, current=new_order)))
        # self.invalid_orders_change_request = {}
        for name, data in self.invalid_orders_change_request.items():
            status, message = data
            orders_history[self.registered_articles[name].order].append(html_reports.p_message(status) + html_reports.tag('p', _('Unable to change order: {previous} to {current}. ').format(previous=self.registered_articles[name].order, current=self.pkg_articles[name].order)) + html_reports.tag('p', message))
        #self.requested_new_order = {}
        for name, order in self.requested_new_order.items():
            if not order in orders.keys():
                orders[order] = []
            orders[order].append(name)

            if not order in orders_history.keys():
                orders_history[order] = []
            orders_history[order].append(html_reports.tag('p', _('new filename and order: {filename} and {order}').format(filename=name, order=order)))
        return (orders, orders_history)

    def validate_resulting_orders_report(self):
        #resulting_orders
        labels = ['order', _('filename'), _('history'), 'status', _('message')]
        orders, history = self.resulting_orders
        items = []
        for order in sorted(orders.keys()):
            values = []
            status = ''
            msg = ''
            if len(orders[order]) > 1:
                status = validation_status.STATUS_BLOCKING_ERROR
                msg = _('Unique value for {label} is required for all the documents in the package').format(label='order')
            values.append(order)
            values.append(orders[order])
            values.append(''.join(history[order]))
            values.append(status)
            values.append(msg)

            items.append(label_values(labels, values))
        return html_reports.tag('h2', _('Orders validations')) + html_reports.sheet(labels, items, html_cell_content=[_('message'), _('history')])


class ArticlesSetValidations(object):

    def __init__(self, pkg, articles_data, logger):
        self.logger = logger
        self.pkg = pkg
        self.articles_data = articles_data
        self.registered_articles = {}
        self.is_db_generation = articles_data.articles_db_manager is not None
        if articles_data.articles_db_manager is not None:
            self.registered_articles = articles_data.articles_db_manager.registered_articles
        self.merged_articles = self.registered_articles.copy()
        self.merged_articles.update(pkg.pkg_articles)
        self.articles_validations = {}
        self.updated_articles = {}

        self.ERROR_LEVEL_FOR_UNIQUE_VALUES = {'order': validation_status.STATUS_BLOCKING_ERROR, 'doi': validation_status.STATUS_BLOCKING_ERROR, 'elocation id': validation_status.STATUS_BLOCKING_ERROR, 'fpage-lpage-seq-elocation-id': validation_status.STATUS_ERROR}
        if not self.is_db_generation:
            self.ERROR_LEVEL_FOR_UNIQUE_VALUES['order'] = validation_status.STATUS_WARNING

        self.EXPECTED_COMMON_VALUES_LABELS = ['journal-title', 'journal-id (publisher-id)', 'journal-id (nlm-ta)', 'e-ISSN', 'print ISSN', 'publisher name', 'issue label', 'issue pub date', 'license']
        self.REQUIRED_DATA = ['journal-title', 'journal ISSN', 'publisher name', 'issue label', 'issue pub date', ]
        self.EXPECTED_UNIQUE_VALUE_LABELS = ['order', 'doi', 'elocation id', 'fpage-lpage-seq-elocation-id']

    @property
    def articles_common_data(self):
        data = {}
        for label in self.EXPECTED_COMMON_VALUES_LABELS:
            values = {}
            for xml_name, article in self.merged_articles.items():
                value = article.summary[label]

                if not value in values:
                    values[value] = []
                values[value].append(xml_name)

            data[label] = values
        return data

    @property
    def articles_unique_data(self):
        data = {}
        for label in self.EXPECTED_UNIQUE_VALUE_LABELS:
            values = {}
            for xml_name, article in self.merged_articles.items():
                value = article.summary[label]

                if not value in values:
                    values[value] = []
                values[value].append(xml_name)

            data[label] = values
        return data

    @property
    def invalid_xml_name_items(self):
        return sorted([xml_name for xml_name, doc in self.merged_articles.items() if doc.tree is None])

    @property
    def missing_required_values(self):
        required_items = {}
        for label, values in self.articles_common_data.items():
            if None in values.keys():
                required_items[label] = values[None]
        return required_items

    @property
    def conflicting_values(self):
        data = {}
        for label, values in self.articles_common_data.items():
            if len(values) > 1:
                data[label] = values
        return data

    @property
    def duplicated_values(self):
        duplicated_labels = {}
        for label, values in self.articles_unique_data.items():
            if len(values) > 0 and len(values) != len(self.articles):

                duplicated = {value: xml_files for value, xml_files in values.items() if len(xml_files) > 1}

                if len(duplicated) > 0:
                    duplicated_labels[label] = duplicated
        return duplicated_labels

    @property
    def compiled_affiliations(self):
        evaluation = {}
        keys = [_('authors without aff'), 
                _('authors with more than 1 affs'), 
                _('authors with invalid xref[@ref-type=aff]'), 
                _('incomplete affiliations')]
        for k in keys:
            evaluation[k] = []

        for xml_name, doc in self.merged_articles.items():
            aff_ids = [aff.id for aff in doc.affiliations]
            for contrib in doc.contrib_names:
                if len(contrib.xref) == 0:
                    evaluation[_('authors without aff')].append(xml_name)
                elif len(contrib.xref) > 1:
                    valid_xref = [xref for xref in contrib.xref if xref in aff_ids]
                    if len(valid_xref) != len(contrib.xref):
                        evaluation[_('authors with invalid xref[@ref-type=aff]')].append(xml_name)
                    elif len(valid_xref) > 1:
                        evaluation[_('authors with more than 1 affs')].append(xml_name)
                    elif len(valid_xref) == 0:
                        evaluation[_('authors without aff')].append(xml_name)
            for aff in doc.affiliations:
                if None in [aff.id, aff.i_country, aff.norgname, aff.orgname, aff.city, aff.state, aff.country]:
                    evaluation[_('incomplete affiliations')].append(xml_name)
        return evaluation

    def compile_references(self):
        self.sources_and_reftypes = {}
        self.reftype_and_sources = {}
        self.missing_source = []
        self.missing_year = []
        self.unusual_sources = []
        self.unusual_years = []
        self.years = {}
        for xml_name, doc in self.merged_articles.items():
            for ref in doc.references:
                if ref.source is not None:
                    if not ref.source in self.sources_and_reftypes.keys():
                        self.sources_and_reftypes[ref.source] = {}
                    if not ref.publication_type in self.sources_and_reftypes[ref.source].keys():
                        self.sources_and_reftypes[ref.source][ref.publication_type] = []
                    self.sources_and_reftypes[ref.source][ref.publication_type].append(xml_name + ': ' + str(ref.id))

                if not ref.publication_type in self.reftype_and_sources.keys():
                    self.reftype_and_sources[ref.publication_type] = {}
                if not ref.source in self.reftype_and_sources[ref.publication_type].keys():
                    self.reftype_and_sources[ref.publication_type][ref.source] = []
                self.reftype_and_sources[ref.publication_type][ref.source].append(xml_name + ': ' + str(ref.id))

                # year
                if ref.publication_type in attributes.BIBLIOMETRICS_USE:
                    if not ref.year in self.years.keys():
                        self.years[ref.year] = []
                    self.years[ref.year].append(xml_name + ': ' + str(ref.id))
                    if ref.year is None:
                        self.missing_year.append([xml_name, ref.id])
                    else:
                        if not ref.year.isdigit():
                            self.unusual_years.append([xml_name, ref.id, ref.year])

                    if ref.source is None:
                        self.missing_source.append([xml_name, ref.id])
                    else:
                        if ref.source.isdigit():
                            self.unusual_sources.append([xml_name, ref.id, ref.source])
        self.bad_sources_and_reftypes = {source: reftypes for source, reftypes in self.sources_and_reftypes.items() if len(reftypes) > 1}

    @property
    def is_processed_in_batches(self):
        return any([self.is_aop_issue, self.is_rolling_pass])

    @property
    def is_aop_issue(self):
        return any([a.is_ahead for a in self.merged_articles.values()])

    @property
    def is_rolling_pass(self):
        _is_rolling_pass = False
        if not self.is_aop_issue:
            epub_dates = list(set([a.epub_dateiso for a in self.merged_articles.values() if a.epub_dateiso is not None]))
            epub_ppub_dates = [a.epub_ppub_dateiso for a in self.merged_articles.values() if a.epub_ppub_dateiso is not None]
            collection_dates = [a.collection_dateiso for a in self.merged_articles.values() if a.collection_dateiso is not None]
            other_dates = list(set(epub_ppub_dates + collection_dates))
            if len(epub_dates) > 0:
                if len(other_dates) == 0:
                    _is_rolling_pass = True
                elif len(other_dates) > 1:
                    _is_rolling_pass = True
                elif len([None for a in self.merged_articles.values() if a.collection_dateiso is None]) > 0:
                    _is_rolling_pass = True
        return _is_rolling_pass

    @property
    def articles(self):
        return articles_sorted_by_order(self.merged_articles)

    @property
    def pkg_journal_validations_report_title(self):
        signal = ''
        msg = ''
        if not self.is_db_generation:
            signal = '<sup>*</sup>'
            msg = html_reports.tag('h5', '<a name="note"><sup>*</sup></a>' + _('Journal data in the XML files must be consistent with {link}').format(link=html_reports.link('http://static.scielo.org/sps/titles-tab-v2-utf-8.csv', 'http://static.scielo.org/sps/titles-tab-v2-utf-8.csv')), 'note')
        return html_reports.tag('h2', _('Journal data: XML files and registered data') + signal) + msg

    def validate(self, doi_services, dtd_files, articles_work_area):
        self.logger.register('compile_references')
        self.compile_references()

        self.logger.register('pkg_journal_validations')
        self.pkg_journal_validations = PackageValidationsResult()
        self.pkg_journal_validations.title = self.pkg_journal_validations_report_title

        self.logger.register('pkg_reg_issue_validations')
        self.pkg_reg_issue_validations = PackageValidationsResult()
        self.pkg_reg_issue_validations.title = html_reports.tag('h2', _('Checking issue data: XML files and registered data'))

        self.logger.register('articles validations - prep')
        self.articles_validations = {}
        xml_journal_data_validator = XMLJournalDataValidator(self.articles_data.journal_data)
        xml_issue_data_validator = XMLIssueDataValidator(self.is_db_generation, self.articles_data.issue_error_msg, self.articles_data.issue_models)
        xml_structure_validator = XMLStructureValidator(dtd_files)
        xml_content_validator = XMLContentValidator(doi_services, self.articles_data)

        self.logger.register('articles validations')
        self.articles_validations = {}
        for name, article in self.merged_articles.items():
            self.logger.register('validate ' + name)
            self.articles_validations[name] = ArticleValidations(articles_work_area[name], self.pkg.is_xml_generation, self.is_db_generation)
            self.articles_validations[name].validations_file['journal'].message = xml_journal_data_validator.validate(article)
            self.articles_validations[name].validations_file['issue'].message = xml_issue_data_validator.validate(article)
            self.articles_validations[name].validations_file['xmlstructure'].message = xml_structure_validator.validate(articles_work_area[name])
            self.articles_validations[name].validations_file['xmlcontent'].message, self.articles_validations[name].article_display_report = xml_content_validator.validate(article, self.pkg.pkg_path, articles_work_area[name], self.pkg.is_xml_generation)

            self.pkg_journal_validations[name] = self.articles_validations[name].validations_file['journal']
            self.pkg_reg_issue_validations[name] = self.articles_validations[name].validations_file['issue']

        self.logger.register('consistency validations')
        self.consistency_validations = ValidationsResult()
        self.consistency_validations.message = self.consistency_validations_report

        self.logger.register('xc pre validations')
        self.xc_pre_validations = ValidationsResult()
        self.xc_pre_validations.message = OrderValidations(self.registered_articles, self.pkg.pkg_articles).report_content()
        self.logger.register('xc pre validations - fim')

    @property
    def detailed_report(self):
        labels = ['file', 'order', _('pages'), _('article'), 'aop pid/related', _('reports')]
        widths = {}
        widths['file'] = '10'
        widths['order'] = '5'
        widths[_('pages')] = '5'
        widths[_('article')] = '60'
        widths['aop pid/related'] = '10'
        widths[_('reports')] = '10'

        items = []
        for new_name, article in self.articles:
            hide_and_show_block_items = self.articles_validations[new_name].hide_and_show_block('view-reports-')
            values = []
            values.append(new_name)
            values.append(article.order)
            values.append(article.pages)
            if self.articles_validations[new_name].article_display_report is None:
                values.append('')
            else:
                values.append(self.articles_validations[new_name].article_display_report.table_of_contents)
            related = {}
            for k, v in {'aop doi': article.previous_pid, 'related': [item.get('xml', '') for item in article.related_articles]}.items():
                if v is not None:
                    if len(v) > 0:
                        related[k] = v
            values.append(related)
            items.append((values, hide_and_show_block_items))
        report = html_reports.HideAndShowBlocksReport(labels, items, html_cell_content=[_('article')], widths=widths)
        return report.content

    @property
    def toc_extended_report(self):
        labels = ['file', _('article'), 'pdf']
        widths = {'file': '10', _('article'): '40', 'pdf': '50'}
        items = []
        for new_name, article in self.articles:
            values = []
            values.append(new_name)
            if self.articles_validations[new_name].article_display_report is None:
                values.append('')
                values.append('')
            else:
                values.append(self.articles_validations[new_name].article_display_report.table_of_contents_detailed)
                values.append(self.articles_validations[new_name].article_display_report.pdf_items)
            items.append(label_values(labels, values))
        return html_reports.sheet(labels, items, table_style='reports-sheet', html_cell_content=[_('article'), 'pdf'], widths=widths)

    @property
    def article_db_status_report(self, new_name):
        labels = [
            _('type'),
            _('creation date'),
            _('last update'),
            _('order'),
            _('pages'),
            _('aop PID'),
            _('doi'),
            _('authors'),
            _('title'),
        ]
        rows = []
        articles = [self.registered_articles.get('new_name'), self.pkg.pkg_articles.get('new_name'), self.updated_articles.get('new_name')]
        types = [_('registered, before converting'), _('package'), _('registered, after converting')]
        for tp, a in zip(types, articles):
            if a is not None:
                values = []
                values.append(tp)
                values.append(a.creation_date_display)
                values.append(a.last_update_display)
                values.append(a.order)
                values.append(a.pages)
                values.append(a.previous_article_pid)
                values.append(a.doi)
                values.append('; '.join(article.authors_list(a.article_contrib_items)))
                values.append(article.title)
                rows.append(label_values(labels, values))
        return html_reports.sheet(labels, rows, table_style='reports-sheet', html_cell_content=['title'])

    @property
    def db_status_report(self):
        labels = ['file', _('article'), _('processing history')]
        items = []
        for new_name, article in self.articles:
            report_id = 'dbstatus-'
            block_parent_id = report_id + new_name
            block_items = [html_reports.HideAndShowBlockItem(block_parent_id, _('processing history'), 'db-hist-' + new_name, 'datarep', self.article_db_status_report(new_name), '')]
            hide_and_show_block_items = html_reports.HideAndShowBlock(block_parent_id, block_items)
            values = []
            values.append(new_name)
            values.append(self.articles_validations[new_name].article_display_report.table_of_contents)
            items.append((values, hide_and_show_block_items))
        report = html_reports.HideAndShowBlocksReport(labels, items, html_cell_content=[_('article')])
        return report.content

    @property
    def articles_dates_report(self):
        labels = ['name', '@article-type',
        'received', 'accepted', 'receive to accepted (days)', 'article date', 'issue date', 'accepted to publication (days)', 'accepted to today (days)']
        items = []
        for xml_name, doc in self.articles:
            values = []
            values.append(xml_name)
            values.append(doc.article_type)
            values.append(article_utils.display_date(doc.received_dateiso))
            values.append(article_utils.display_date(doc.accepted_dateiso))
            values.append(str(doc.history_days))
            values.append(article_utils.display_date(doc.article_pub_dateiso))
            values.append(article_utils.display_date(doc.issue_pub_dateiso))
            values.append(str(doc.publication_days))
            values.append(str(doc.registration_days))
            items.append(label_values(labels, values))
        article_dates = html_reports.sheet(labels, items, 'dbstatus')

        labels = [_('year'), _('location')]
        items = []
        for year in sorted(self.years.keys()):
            values = []
            values.append(year)
            values.append(self.years[year])
            items.append(label_values(labels, values))
        reference_dates = html_reports.sheet(labels, items, 'dbstatus')

        return html_reports.tag('h4', _('Articles Dates Report')) + article_dates + reference_dates

    @property
    def articles_affiliations_report(self):
        r = html_reports.tag('h4', _('Affiliations Report'))
        items = []
        for label, occs in self.compiled_affiliations.items():
            items.append({'label': label, 'quantity': str(len(occs)), _('files'): sorted(list(set(occs)))})
        r += html_reports.sheet(['label', 'quantity', _('files')], items, 'dbstatus')
        return r

    @property
    def references_overview_report(self):
        labels = ['label', 'status', 'message', _('why it is not a valid message?')]
        items = []
        values = []
        values.append(_('references by type'))
        values.append(validation_status.STATUS_INFO)
        values.append({reftype: str(sum([len(occ) for occ in sources.values()])) for reftype, sources in self.reftype_and_sources.items()})
        values.append('')
        items.append(label_values(labels, values))

        if len(self.bad_sources_and_reftypes) > 0:
            values = []
            values.append(_('same sources as different types references'))
            values.append(validation_status.STATUS_ERROR)
            values.append(self.bad_sources_and_reftypes)
            values.append('')
            items.append(label_values(labels, values))

        if len(self.missing_source) > 0:
            items.append({'label': _('references missing source'), 'status': validation_status.STATUS_ERROR, 'message': [' - '.join(item) for item in self.missing_source], _('why it is not a valid message?'): ''})
        if len(self.missing_year) > 0:
            items.append({'label': _('references missing year'), 'status': validation_status.STATUS_ERROR, 'message': [' - '.join(item) for item in self.missing_year], _('why it is not a valid message?'): ''})
        if len(self.unusual_sources) > 0:
            items.append({'label': _('references with unusual value for source'), 'status': validation_status.STATUS_ERROR, 'message': [' - '.join(item) for item in self.unusual_sources], _('why it is not a valid message?'): ''})
        if len(self.unusual_years) > 0:
            items.append({'label': _('references with unusual value for year'), 'status': validation_status.STATUS_ERROR, 'message': [' - '.join(item) for item in self.unusual_years], _('why it is not a valid message?'): ''})

        return html_reports.tag('h4', _('Package references overview')) + html_reports.sheet(labels, items, table_style='dbstatus')

    @property
    def sources_overview_report(self):
        labels = ['source', _('location')]
        h = None
        if len(self.reftype_and_sources) > 0:
            h = ''
            for reftype, sources in self.reftype_and_sources.items():
                items = []
                h += html_reports.tag('h4', reftype)
                for source in sorted(sources.keys()):
                    items.append({'source': source, _('location'): sources[source]})
                h += html_reports.sheet(labels, items, 'dbstatus')
        return h

    @property
    def pages_report(self):
        # FIXME
        results = []
        previous_lpage = None
        previous_xmlname = None
        int_previous_lpage = None

        for xml_name, article in self.articles:
            fpage = article.fpage
            lpage = article.lpage
            msg = []
            status = ''
            if article.pages == '':
                msg.append(_('no pagination was found'))
                if not article.is_ahead:
                    status = validation_status.STATUS_ERROR
            if fpage is not None and lpage is not None:
                if fpage.isdigit() and lpage.isdigit():
                    int_fpage = int(fpage)
                    int_lpage = int(lpage)

                    #if not article.is_rolling_pass and not article.is_ahead:
                    if int_previous_lpage is not None:
                        if int_previous_lpage > int_fpage:
                            status = validation_status.STATUS_BLOCKING_ERROR if not article.is_epub_only else validation_status.STATUS_WARNING
                            msg.append(_('Invalid pages') + ': ' + _('check lpage={lpage} ({previous_article}) and fpage={fpage} ({xml_name})').format(previous_article=previous_xmlname, xml_name=xml_name, lpage=previous_lpage, fpage=fpage))
                        elif int_previous_lpage == int_fpage:
                            status = validation_status.STATUS_WARNING
                            msg.append(_('lpage={lpage} ({previous_article}) and fpage={fpage} ({xml_name}) are the same').format(previous_article=previous_xmlname, xml_name=xml_name, lpage=previous_lpage, fpage=fpage))
                        elif int_previous_lpage + 1 < int_fpage:
                            status = validation_status.STATUS_WARNING
                            msg.append(_('there is a gap between lpage={lpage} ({previous_article}) and fpage={fpage} ({xml_name})').format(previous_article=previous_xmlname, xml_name=xml_name, lpage=previous_lpage, fpage=fpage))
                    if int_fpage > int_lpage:
                        status = validation_status.STATUS_BLOCKING_ERROR
                        msg.append(_('Invalid page range'))
                    int_previous_lpage = int_lpage
                    previous_lpage = lpage
                    previous_xmlname = xml_name
            #dates = '|'.join([item if item is not None else 'none' for item in [article.epub_ppub_dateiso, article.collection_dateiso, article.epub_dateiso]])
            msg = '; '.join(msg)
            if len(msg) > 0:
                msg = '. ' + msg
            results.append({'label': xml_name, 'status': status, 'message': article.pages + msg, _('why it is not a valid message?'): ''})
        return html_reports.tag('h2', _('Pages Report')) + html_reports.tag('div', html_reports.sheet(['label', 'status', 'message', _('why it is not a valid message?')], results, table_style='validation'))

    @property
    def journal_issue_header_report(self):
        articles_common_data = ''
        for label, values in self.articles_common_data.items():
            message = ''
            if len(values.keys()) == 1:
                articles_common_data += html_reports.tag('p', html_reports.display_label_value(label, values.keys()[0]))
            else:
                articles_common_data += html_reports.format_list(label + ':', 'ol', values.keys())
        return html_reports.tag('h2', _('Data in the XML Files')) + html_reports.tag('div', articles_common_data, 'issue-data')

    @property
    def invalid_xml_report(self):
        r = ''
        if len(self.invalid_xml_name_items) > 0:
            r += html_reports.tag('div', html_reports.p_message(_('{status}: invalid XML files.').format(status=validation_status.STATUS_BLOCKING_ERROR)))
            r += html_reports.tag('div', html_reports.format_list('', 'ol', self.invalid_xml_name_items, 'issue-problem'))
        return r

    @property
    def missing_items_report(self):
        r = ''
        for label, items in self.missing_required_values.items():
            r += html_reports.tag('div', html_reports.p_message(_('{status}: missing {label} in: ').format(status=validation_status.STATUS_BLOCKING_ERROR, label=label)))
            r += html_reports.tag('div', html_reports.format_list('', 'ol', items, 'issue-problem'))
        return r

    @property
    def duplicated_values_report(self):
        parts = []
        for label, values in self.duplicated_values.items():
            status = self.ERROR_LEVEL_FOR_UNIQUE_VALUES[label]
            _m = _('Unique value for {label} is required for all the documents in the package').format(label=label)
            parts.append(html_reports.p_message(status + ': ' + _m))
            for value, xml_files in values.items():
                parts.append(html_reports.format_list(_('found {label}="{value}" in:').format(label=label, value=value), 'ul', xml_files, 'issue-problem'))
        return ''.join(parts)

    @property
    def conflicting_values_report(self):
        parts = []
        for label, values in self.conflicting_values.items():
            compl = ''
            _status = validation_status.STATUS_BLOCKING_ERROR
            if label == 'issue pub date':
                if self.is_rolling_pass:
                    _status = validation_status.STATUS_WARNING
            elif label == 'license':
                _status = validation_status.STATUS_WARNING
            _m = _('{status}: same value for {label} is required for all the documents in the package.').format(status=_status, label=label)
            parts.append(html_reports.p_message(_m))
            parts.append(html_reports.tag('div', html_reports.format_html_data(values), 'issue-problem'))
        return ''.join(parts)

    @property
    def consistency_validations_report(self):
        text = []
        text += self.invalid_xml_report
        text += self.missing_items_report
        text += self.conflicting_values_report
        text += self.duplicated_values_report
        text = html_reports.tag('div', ''.join(text), 'issue-messages')
        text += self.pages_report
        return html_reports.tag('h2', _('Checking issue data consistency')) + text

    @property
    def journal_and_issue_report(self):
        report = []
        report.append(self.journal_issue_header_report)
        report.append(self.pkg_journal_validations.report(errors_only=not self.pkg.is_xml_generation))
        report.append(self.pkg_reg_issue_validations.report(errors_only=not self.pkg.is_xml_generation))
        if self.consistency_validations.total() > 0:
            report.append(self.consistency_validations.message)
        report.append(self.xc_pre_validations.message)
        return ''.join(report)

    @property
    def blocking_errors(self):
        return self.consistency_validations.blocking_errors + self.pkg_reg_issue_validations.blocking_errors + self.xc_pre_validations.blocking_errors

    @property
    def fatal_errors(self):
        return sum([article_validations.fatal_errors for article_validations in self.articles_validations.validations_file.values()])


class ReportsMaker(object):

    def __init__(self, articles_set_validations, xpm_version=None, conversion_reports=None, display_report=False):
        self.display_report = display_report
        self.processing_result_location = None
        self.articles_set_validations = articles_set_validations
        self.conversion_reports = conversion_reports
        self.xpm_version = xpm_version
        self.tabs = ['pkg-files', 'summary-report', 'issue-report', 'toc-extended', 'individual-report', 'references', 'dates-report', 'aff-report', 'conversion-report', 'db-overview']
        self.labels = {
            'pkg-files': _('Files/Folders'),
            'summary-report': _('Summary'),
            'issue-report': 'journal/issue',
            'individual-report': _('XML Validations'),
            'conversion-report': _('Conversion'),
            'db-overview': _('Database'),
            'aff-report': _('Affiliations'),
            'dates-report': _('Dates'),
            'references': _('References'),
            'toc-extended': _('ToC'),
        }

    @property
    def report_components(self):
        components = {}
        components['pkg-files'] = self.articles_set_validations.pkg.xml_list
        if self.processing_result_location is not None:
            components['pkg-files'] += processing_result_location(self.processing_result_location)

        components['summary-report'] = ''
        components['individual-report'] = self.articles_set_validations.detailed_report
        components['aff-report'] = self.articles_set_validations.articles_affiliations_report
        components['dates-report'] = self.articles_set_validations.articles_dates_report
        components['references'] = (self.articles_set_validations.references_overview_report +
            self.articles_set_validations.sources_overview_report)

        if not self.articles_set_validations.pkg.is_xml_generation:
            components['toc-extended'] = self.articles_set_validations.toc_extended_report
            components['issue-report'] = self.articles_set_validations.journal_and_issue_report

        if self.conversion_reports is not None:
            if self.conversion_reports.issue_error_msg != '':
                components['issue-report'] = self.conversion_reports.issue_error_msg
            components['conversion-report'] = self.conversion_reports.xc_pre_validations_report
            components['db-overview'] = self.conversion_reports.db_status_report
            components['summary-report'] = self.conversion_reports.xc_conclusion_msg + self.conversion_reports.xc_results_report + self.conversion_reports.aop_results_report

        validations = ValidationsResult()
        validations.message = html_reports.join_texts(components.values())
        components['summary-report'] = error_msg_subtitle() + validations.statistics_display(False) + components['summary-report']
        components = {k: label_errors(v) for k, v in components.items()}
        return components

    @property
    def footnote(self):
        content = html_reports.tag('p', _('finished'))
        if self.xpm_version is not None:
            content += html_reports.tag('p', _('report generated by XPM ') + self.xpm_version)
        return content

    def save_report(self, report_path, report_filename, report_title):
        self.tabbed_report = html_reports.TabbedReport(self.labels, self.tabs, self.report_components, 'summary-report', self.footnote)
        self.tabbed_report.save_report(report_path, report_filename, report_title, self.display_report)


def extract_report_core(content):
    report = ''
    if 'Parse/validation finished' in content and '<!DOCTYPE' in content:
        part1 = content[0:content.find('<!DOCTYPE')]
        part2 = content[content.find('<!DOCTYPE'):]

        l = part1[part1.rfind('Line number:')+len('Line number:'):]
        l = l[0:l.find('Column')]
        l = ''.join([item.strip() for item in l.split()])
        if l.isdigit():
            l = str(int(l) + 1) + ':'
            if l in part2:
                part2 = part2[0:part2.find(l)] + '\n...'

        part1 = part1.replace('\n', '<br/>')
        part2 = part2.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>').replace('\t', '&nbsp;'*4)
        report = '<p>' + part1 + part2 + '</p>'
    elif '</body>' in content:
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        content = content[content.find('<body'):]
        content = content[0:content.rfind('</body>')]
        report = content[content.find('>')+1:]
    elif '<body' in content:
        if not isinstance(content, unicode):
            content = content.decode('utf-8')
        content = content[content.find('<body'):]
        report = content[content.find('>')+1:]
    elif not '<' in content:
        report = content.replace('\n', '<br/>')
    return report


def label_values(labels, values):
    r = {}
    for i in range(0, len(labels)):
        r[labels[i]] = values[i]
    return r


def evaluate_journal_data(items):
    unmatched = []
    for label, value, expected_values, err_msg in items:
        if expected_values is None or expected_values == '':
            expected_values = _('no value')
        if not isinstance(expected_values, list):
            expected_values = [expected_values]
        expected_values_msg = _(' or ').join(expected_values)
        value = _('no value') if value is None else value.strip()
        if len(expected_values) == 0:
            expected_values_msg = _('no value')
            status = validation_status.STATUS_WARNING if value != expected_values_msg else validation_status.STATUS_OK
        else:
            status = validation_status.STATUS_OK
            if not value in expected_values:
                if label == _('license'):
                    status = err_msg
                    for expected_value in expected_values:
                        if '/' + expected_value.lower() + '/' in str(value) + '/':
                            status = validation_status.STATUS_OK
                            break
                else:
                    status = err_msg
        if status != validation_status.STATUS_OK:
            unmatched.append({_('data'): label, 'status': status, _('in XML'): value, _('registered journal data') + '*': expected_values_msg, _('why it is not a valid message?'): ''})

    validations_result = ''
    if len(unmatched) > 0:
        validations_result = html_reports.sheet([_('data'), 'status', _('in XML'), _('registered journal data') + '*', _('why it is not a valid message?')], unmatched, table_style='dbstatus')
    return validations_result


def processing_result_location(result_path):
    return '<h5>' + _('Result of the processing:') + '</h5>' + '<p>' + html_reports.link('file:///' + result_path, result_path) + '</p>'


def display_report(report_filename):
    try:
        webbrowser.open('file:///' + report_filename.replace('//', '/').encode(encoding=sys.getfilesystemencoding()), new=2)
    except:
        pass


def articles_sorted_by_order(articles):
    l = sorted([(article.order, xml_name) for xml_name, article in articles.items()])
    l = [(xml_name, articles[xml_name]) for order, xml_name in l]
    return l


def max_score(quote, score):
    return ((score * quote) / 100) + 1


def db_status_item_row(article, history):
    labels = ['order', 'name', 'article title', 'creation date | last update', 'history']
    _source = source
    if source == 'registered':
        _source = 'database'
        _dates = str(article.creation_date_display) + ' / ' + str(article.last_update_display)
    else:
        _dates = ''

    values = []
    values.append(article.order)
    values.append(article.xml_name)
    values.append(_dates)
    values.append(article.title)
    values.append(history)
    return (labels, values)


def error_msg_subtitle():
    msg = html_reports.tag('p', _('Blocking error - indicates errors of data consistency'))
    msg += html_reports.tag('p', _('Fatal error - indicates errors which impact on the quality of the bibliometric indicators and other services'))
    msg += html_reports.tag('p', _('Error - indicates the other kinds of errors'))
    msg += html_reports.tag('p', _('Warning - indicates that something can be an error or something needs more attention'))
    return html_reports.tag('div', msg, 'subtitle')


def label_errors(content):
    content = label_errors_type(content, validation_status.STATUS_BLOCKING_ERROR, 'B')
    content = label_errors_type(content, validation_status.STATUS_FATAL_ERROR, 'F')
    content = label_errors_type(content, validation_status.STATUS_ERROR, 'E')
    content = label_errors_type(content, validation_status.STATUS_WARNING, 'W')
    return content


def label_errors_type(content, error_type, prefix):
    new = []
    i = 0
    content = content.replace(error_type, '~BREAK~' + error_type)
    for part in content.split('~BREAK~'):
        if part.startswith(error_type):
            i += 1
            part = part.replace(error_type, error_type + ' [' + prefix + str(i) + ']')
        new.append(part)
    return ''.join(new)


def word_counter(content, word):
    return len(content.split(word)) - 1


def number_after_words(content, text='Total of errors = '):
    n = 0
    if text in content:
        content = content[content.find(text) + len(text):]
        finished = False
        n = ''
        while not finished and len(content) > 0:
            if content[0].isdigit():
                n += content[0]
                content = content[1:]
            else:
                finished = True

        if len(n) > 0:
            n = int(n)
        else:
            n = 0
    return n


def rst_title(title):
    return '\n\n' + title + '\n' + '-'*len(title) + '\n'
