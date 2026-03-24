import os
import matplotlib
matplotlib.use('Agg')

from jinja2 import Environment, FileSystemLoader
import matplotlib.pyplot as plt
from datetime import datetime
import logging

try:
    import pdfkit
    PDFKIT_AVAILABLE = True
except ImportError:
    PDFKIT_AVAILABLE = False


class ReportGenerator:
    def __init__(self, config):
        self.config = config.get('reporting', {})
        self.output_dir = self.config.get('output_dir', './reports/generated')
        self.image_dir = os.path.join(self.output_dir, 'images')

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.image_dir, exist_ok=True)

        template_path = os.path.join(os.path.dirname(__file__), 'templates')
        self.template_env = Environment(loader=FileSystemLoader(template_path))

        self.logger = logging.getLogger('ReportGenerator')
        self.logger.setLevel(logging.INFO)

        self.severity_map = {
            'FACE_DISAPPEARED': 1,
            'GAZE_AWAY': 2,
            'MOUTH_MOVING': 3,
            'MULTIPLE_FACES': 4,
            'OBJECT_DETECTED': 5,
            'AUDIO_DETECTED': 3
        }

    def generate_report(self, student_info, violations, output_format='pdf'):
        """
        Generate exam violation report.
        Falls back to HTML if PDF generation is unavailable.
        """
        try:
            report_data = {
                'student': student_info,
                'violations': violations,
                'generated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'stats': self._calculate_stats(violations),
                'timeline_image': self._generate_timeline(violations, student_info['id']),
                'heatmap_image': self._generate_heatmap(violations, student_info['id']),
                'has_images': False
            }

            if report_data['timeline_image'] or report_data['heatmap_image']:
                report_data['has_images'] = True

            template = self.template_env.get_template('base_report.html')
            html_content = template.render(report_data)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_filename = f"report_{student_info['id']}_{timestamp}"

            # Always generate HTML
            html_path = os.path.join(self.output_dir, f"{base_filename}.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            self.logger.info(f"HTML report generated at: {html_path}")

            # Try PDF generation if requested
            if output_format.lower() == 'pdf' and PDFKIT_AVAILABLE:
                try:
                    wkhtmltopdf_path = self.config.get('wkhtmltopdf_path')
                    pdf_config = (
                        pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
                        if wkhtmltopdf_path else None
                    )

                    pdf_path = os.path.join(self.output_dir, f"{base_filename}.pdf")

                    options = {
                        'enable-local-file-access': None,
                        'quiet': '',
                        'margin-top': '10mm',
                        'margin-right': '10mm',
                        'margin-bottom': '10mm',
                        'margin-left': '10mm'
                    }

                    pdfkit.from_string(
                        html_content,
                        pdf_path,
                        options=options,
                        configuration=pdf_config
                    )

                    self.logger.info(f"PDF report generated at: {pdf_path}")
                    return pdf_path

                except Exception as e:
                    self.logger.warning(
                        f"PDF generation failed, using HTML instead: {str(e)}"
                    )

            return html_path

        except Exception as e:
            self.logger.error(f"Report generation failed: {str(e)}")
            return None

    def _calculate_stats(self, violations):
        stats = {
            'total': len(violations),
            'by_type': {},
            'timeline': [],
            'severity_score': 0,
            'average_severity': 0
        }

        for v in violations:
            stats['by_type'][v['type']] = stats['by_type'].get(v['type'], 0) + 1
            severity = self.severity_map.get(v['type'], 1)
            stats['severity_score'] += severity
            stats['timeline'].append({
                'time': v['timestamp'],
                'type': v['type'],
                'severity': severity
            })

        if stats['total'] > 0:
            stats['average_severity'] = stats['severity_score'] / stats['total']

        return stats

    def _generate_timeline(self, violations, student_id):
        if not violations:
            return None

        try:
            times, severities, labels = [], [], []

            for v in violations:
                times.append(datetime.strptime(v['timestamp'], "%Y%m%d_%H%M%S_%f"))
                severities.append(self.severity_map.get(v['type'], 1))
                labels.append(v['type'])

            plt.figure(figsize=(12, 5))
            plt.plot(times, severities, 'o-', markersize=6)

            for t, s, lbl in zip(times, severities, labels):
                plt.annotate(lbl, (t, s), xytext=(0, 8),
                             textcoords="offset points",
                             ha='center', fontsize=8)

            plt.title(f"Violation Timeline - {student_id}")
            plt.xlabel("Time")
            plt.ylabel("Severity")
            plt.grid(True, linestyle='--', alpha=0.6)
            plt.xticks(rotation=45)
            plt.tight_layout()

            path = os.path.join(self.image_dir, f'timeline_{student_id}.png')
            plt.savefig(path, dpi=150)
            plt.close()
            return path

        except Exception as e:
            self.logger.warning(f"Timeline generation failed: {str(e)}")
            return None

    def _generate_heatmap(self, violations, student_id):
        if not violations:
            return None

        try:
            counts = {}
            for v in violations:
                counts[v['type']] = counts.get(v['type'], 0) + 1

            types, values = zip(*sorted(counts.items(), key=lambda x: x[1]))

            plt.figure(figsize=(10, 5))
            colors = [plt.cm.Reds(self.severity_map.get(t, 1)/5) for t in types]

            bars = plt.barh(types, values, color=colors)
            for bar in bars:
                plt.text(bar.get_width() + 0.2,
                         bar.get_y() + bar.get_height()/2,
                         str(int(bar.get_width())),
                         va='center')

            plt.title(f"Violation Frequency - {student_id}")
            plt.xlabel("Count")
            plt.tight_layout()

            path = os.path.join(self.image_dir, f'heatmap_{student_id}.png')
            plt.savefig(path, dpi=150)
            plt.close()
            return path

        except Exception as e:
            self.logger.warning(f"Heatmap generation failed: {str(e)}")
            return None
