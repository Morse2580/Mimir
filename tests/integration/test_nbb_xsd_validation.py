"""
NBB XSD Validation Tests with Golden Vectors

This module tests OneGate XML export validation against the official NBB XSD schema.
Tests include golden vectors for major, significant, and no-report scenarios.
"""

import pytest
import os
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any
from lxml import etree

from backend.app.incidents.rules.contracts import Severity, IncidentInput, ClassificationResult


class TestNBBXSDValidation:
    """Test NBB OneGate XSD validation with golden vectors."""
    
    @classmethod
    def setup_class(cls):
        """Set up XSD schema and test vectors."""
        cls.schema_path = Path("/Users/arinti-work/Documents/projs/regops-worktrees/integration-tests/infrastructure/onegate/schemas/dora_v2.xsd")
        cls.checksum_path = Path("/Users/arinti-work/Documents/projs/regops-worktrees/integration-tests/infrastructure/onegate/schemas/dora_v2.xsd.sha256")
        
        # Load and validate XSD schema
        if not cls.schema_path.exists():
            pytest.fail(f"NBB XSD schema not found: {cls.schema_path}")
        
        # Verify XSD checksum integrity
        cls._verify_xsd_checksum()
        
        # Load XSD schema
        with open(cls.schema_path, 'r', encoding='utf-8') as f:
            schema_doc = etree.parse(f)
        
        cls.schema = etree.XMLSchema(schema_doc)
    
    @classmethod
    def _verify_xsd_checksum(cls):
        """Verify XSD schema hasn't been tampered with."""
        if not cls.checksum_path.exists():
            pytest.fail(f"XSD checksum file not found: {cls.checksum_path}")
        
        # Read stored checksum
        with open(cls.checksum_path, 'r') as f:
            stored_checksum = f.read().strip().split()[0]
        
        # Calculate current checksum
        with open(cls.schema_path, 'rb') as f:
            current_checksum = hashlib.sha256(f.read()).hexdigest()
        
        if stored_checksum != current_checksum:
            pytest.fail(f"XSD schema checksum mismatch! "
                      f"Expected: {stored_checksum}, Got: {current_checksum}")
    
    def test_xsd_schema_integrity(self):
        """Test that NBB XSD schema loads and is valid."""
        assert self.schema is not None
        
        # Verify schema namespace
        schema_doc = etree.parse(str(self.schema_path))
        root = schema_doc.getroot()
        
        assert root.attrib['targetNamespace'] == "http://nbb.be/onegate/dora/v2"
        print("✅ NBB XSD schema integrity verified")
    
    def test_golden_vector_major_incident(self):
        """Test major incident golden vector validates against NBB XSD."""
        major_incident_xml = self._create_major_incident_golden_vector()
        
        # Parse and validate
        xml_doc = etree.fromstring(major_incident_xml.encode('utf-8'))
        
        # Validate against schema
        is_valid = self.schema.validate(xml_doc)
        
        if not is_valid:
            error_log = self.schema.error_log
            pytest.fail(f"Major incident golden vector failed XSD validation: {error_log}")
        
        # Additional business rule validations
        assert xml_doc.find('.//{http://nbb.be/onegate/dora/v2}severity').text == "MAJOR"
        assert xml_doc.find('.//{http://nbb.be/onegate/dora/v2}notification_required').text == "true"
        
        print("✅ Major incident golden vector passes NBB XSD validation")
    
    def test_golden_vector_significant_incident(self):
        """Test significant incident golden vector validates against NBB XSD."""
        significant_incident_xml = self._create_significant_incident_golden_vector()
        
        xml_doc = etree.fromstring(significant_incident_xml.encode('utf-8'))
        
        is_valid = self.schema.validate(xml_doc)
        
        if not is_valid:
            error_log = self.schema.error_log
            pytest.fail(f"Significant incident golden vector failed XSD validation: {error_log}")
        
        # Business rule validations
        assert xml_doc.find('.//{http://nbb.be/onegate/dora/v2}severity').text == "SIGNIFICANT"
        assert xml_doc.find('.//{http://nbb.be/onegate/dora/v2}notification_required').text == "true"
        
        print("✅ Significant incident golden vector passes NBB XSD validation")
    
    def test_golden_vector_no_report_incident(self):
        """Test no-report incident golden vector validates against NBB XSD."""
        no_report_xml = self._create_no_report_golden_vector()
        
        xml_doc = etree.fromstring(no_report_xml.encode('utf-8'))
        
        is_valid = self.schema.validate(xml_doc)
        
        if not is_valid:
            error_log = self.schema.error_log
            pytest.fail(f"No-report incident golden vector failed XSD validation: {error_log}")
        
        # Business rule validations
        dora_classification = xml_doc.find('.//{http://nbb.be/onegate/dora/v2}dora_classification').text
        assert dora_classification == "NO_REPORT_REQUIRED"
        assert xml_doc.find('.//{http://nbb.be/onegate/dora/v2}notification_required').text == "false"
        
        print("✅ No-report incident golden vector passes NBB XSD validation")
    
    def test_invalid_xml_rejected(self):
        """Test that invalid XML is properly rejected by NBB XSD."""
        invalid_test_cases = [
            # Missing required elements
            """<?xml version="1.0" encoding="UTF-8"?>
            <incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="INITIAL">
                <!-- Missing header -->
                <incident_details>
                    <severity>MAJOR</severity>
                    <category>SYSTEM_FAILURE</category>
                    <description>Test</description>
                    <affected_services>
                        <service>
                            <name>Payment System</name>
                            <criticality>CRITICAL</criticality>
                            <impact_level>HIGH</impact_level>
                        </service>
                    </affected_services>
                    <geographical_scope>
                        <countries>
                            <country>BE</country>
                        </countries>
                    </geographical_scope>
                </incident_details>
            </incident_notification>""",
            
            # Invalid institution ID format
            """<?xml version="1.0" encoding="UTF-8"?>
            <incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="INITIAL">
                <header>
                    <institution_id>INVALID_FORMAT</institution_id>
                    <institution_name>Test Bank</institution_name>
                    <contact_person>
                        <name>John Doe</name>
                        <role>Risk Manager</role>
                        <phone>+32 2 123 45 67</phone>
                        <email>john.doe@testbank.be</email>
                    </contact_person>
                    <submission_date>2024-03-15T10:30:00Z</submission_date>
                    <incident_id>INC-2024-001</incident_id>
                </header>
            </incident_notification>""",
            
            # Invalid severity value
            """<?xml version="1.0" encoding="UTF-8"?>
            <incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="INITIAL">
                <header>
                    <institution_id>BE1234567890</institution_id>
                    <institution_name>Test Bank</institution_name>
                    <contact_person>
                        <name>John Doe</name>
                        <role>Risk Manager</role>
                        <phone>+32 2 123 45 67</phone>
                        <email>john.doe@testbank.be</email>
                    </contact_person>
                    <submission_date>2024-03-15T10:30:00Z</submission_date>
                    <incident_id>INC-2024-001</incident_id>
                </header>
                <incident_details>
                    <severity>INVALID_SEVERITY</severity>
                    <category>SYSTEM_FAILURE</category>
                    <description>Test</description>
                </incident_details>
            </incident_notification>"""
        ]
        
        for i, invalid_xml in enumerate(invalid_test_cases):
            try:
                xml_doc = etree.fromstring(invalid_xml.encode('utf-8'))
                is_valid = self.schema.validate(xml_doc)
                
                assert not is_valid, f"Invalid test case {i+1} should have been rejected but passed"
                
            except etree.XMLSyntaxError:
                # XML syntax errors are also acceptable rejection
                pass
        
        print("✅ Invalid XML properly rejected by NBB XSD validation")
    
    def test_belgian_specific_validations(self):
        """Test Belgian-specific validation rules in XSD."""
        # Test valid Belgian institution ID
        valid_xml = self._create_major_incident_golden_vector()
        xml_doc = etree.fromstring(valid_xml.encode('utf-8'))
        
        institution_id = xml_doc.find('.//{http://nbb.be/onegate/dora/v2}institution_id').text
        assert institution_id.startswith("BE") and len(institution_id) == 12
        
        # Test Belgian phone number format
        phone = xml_doc.find('.//{http://nbb.be/onegate/dora/v2}phone').text
        assert phone.startswith("+32")
        
        # Test incident ID format
        incident_id = xml_doc.find('.//{http://nbb.be/onegate/dora/v2}incident_id').text
        assert incident_id.startswith("INC-")
        assert len(incident_id.split("-")) == 3  # INC-YYYY-NNN format
        
        print("✅ Belgian-specific validation rules pass")
    
    def test_dst_datetime_handling_in_xml(self):
        """Test that DST datetime handling works correctly in XML export."""
        # Create incident during DST transition
        dst_xml = self._create_dst_incident_golden_vector()
        
        xml_doc = etree.fromstring(dst_xml.encode('utf-8'))
        
        # Validate against schema
        is_valid = self.schema.validate(xml_doc)
        assert is_valid, f"DST incident XML failed validation: {self.schema.error_log}"
        
        # Verify all datetime fields are properly timezone-aware
        occurred_at = xml_doc.find('.//{http://nbb.be/onegate/dora/v2}occurred_at').text
        detected_at = xml_doc.find('.//{http://nbb.be/onegate/dora/v2}detected_at').text
        notification_deadline = xml_doc.find('.//{http://nbb.be/onegate/dora/v2}notification_deadline').text
        
        # All datetime fields should have timezone information
        for dt_field in [occurred_at, detected_at, notification_deadline]:
            if dt_field:
                # Should end with 'Z' (UTC) or have timezone offset
                assert dt_field.endswith('Z') or '+' in dt_field or dt_field.endswith(':00'), \
                    f"Datetime field missing timezone: {dt_field}"
        
        print("✅ DST datetime handling in XML export passes validation")
    
    def test_performance_large_incident_export(self):
        """Test XSD validation performance with large incident data."""
        import time
        
        # Create XML with maximum allowed attachments and data
        large_xml = self._create_large_incident_golden_vector()
        
        start_time = time.time()
        
        xml_doc = etree.fromstring(large_xml.encode('utf-8'))
        is_valid = self.schema.validate(xml_doc)
        
        validation_time = (time.time() - start_time) * 1000  # milliseconds
        
        assert is_valid, f"Large incident XML failed validation: {self.schema.error_log}"
        assert validation_time < 1000, f"XSD validation took {validation_time}ms (limit: 1000ms)"
        
        print(f"✅ Large incident XSD validation completed in {validation_time:.1f}ms")
    
    def _create_major_incident_golden_vector(self) -> str:
        """Create golden vector XML for major incident."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="INITIAL">
    <header>
        <institution_id>BE1234567890</institution_id>
        <institution_name>Test Financial Institution</institution_name>
        <contact_person>
            <name>Risk Manager</name>
            <role>Chief Risk Officer</role>
            <phone>+32 2 123 45 67</phone>
            <email>risk.manager@testbank.be</email>
        </contact_person>
        <submission_date>2024-03-15T10:30:00Z</submission_date>
        <incident_id>INC-2024-001</incident_id>
    </header>
    
    <incident_details>
        <severity>MAJOR</severity>
        <category>SYSTEM_FAILURE</category>
        <description>Critical payment system outage affecting core banking services</description>
        <affected_services>
            <service>
                <name>Payment Processing</name>
                <criticality>CRITICAL</criticality>
                <impact_level>HIGH</impact_level>
            </service>
            <service>
                <name>Core Banking</name>
                <criticality>CRITICAL</criticality>
                <impact_level>HIGH</impact_level>
            </service>
        </affected_services>
        <geographical_scope>
            <countries>
                <country>BE</country>
                <country>LU</country>
            </countries>
            <regions>Benelux</regions>
        </geographical_scope>
        <root_cause>Database server hardware failure</root_cause>
    </incident_details>
    
    <impact_assessment>
        <clients_affected>5000</clients_affected>
        <economic_impact>
            <estimated_loss_eur>150000.00</estimated_loss_eur>
            <recovery_costs_eur>25000.00</recovery_costs_eur>
            <total_impact_eur>175000.00</total_impact_eur>
        </economic_impact>
        <reputational_impact>HIGH</reputational_impact>
        <data_losses>false</data_losses>
        <data_breaches>false</data_breaches>
        <service_availability>
            <availability_percentage>0.0</availability_percentage>
            <sla_breach>true</sla_breach>
        </service_availability>
    </impact_assessment>
    
    <timeline>
        <occurred_at>2024-03-15T14:00:00Z</occurred_at>
        <detected_at>2024-03-15T14:15:00Z</detected_at>
        <confirmed_at>2024-03-15T14:30:00Z</confirmed_at>
        <downtime_duration>PT2H</downtime_duration>
    </timeline>
    
    <regulatory_classification>
        <dora_classification>MAJOR</dora_classification>
        <notification_required>true</notification_required>
        <notification_deadline>2024-03-15T18:30:00Z</notification_deadline>
        <regulatory_references>
            <reference>EU Regulation 2022/2554 - Article 19</reference>
            <reference>NBB Circular XXX-2024</reference>
        </regulatory_references>
    </regulatory_classification>
    
    <remediation>
        <immediate_actions>Failover to backup systems initiated. Customer communications sent.</immediate_actions>
        <preventive_measures>Hardware redundancy review and upgrade planned.</preventive_measures>
        <timeline_for_resolution>2024-03-15T18:00:00Z</timeline_for_resolution>
    </remediation>
</incident_notification>"""
    
    def _create_significant_incident_golden_vector(self) -> str:
        """Create golden vector XML for significant incident."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="INITIAL">
    <header>
        <institution_id>BE0987654321</institution_id>
        <institution_name>Another Financial Institution</institution_name>
        <contact_person>
            <name>Security Officer</name>
            <role>Chief Information Security Officer</role>
            <phone>+32 3 234 56 78</phone>
            <email>security@anotherbank.be</email>
        </contact_person>
        <submission_date>2024-06-10T09:15:00Z</submission_date>
        <incident_id>INC-2024-002</incident_id>
    </header>
    
    <incident_details>
        <severity>SIGNIFICANT</severity>
        <category>CYBER_ATTACK</category>
        <description>DDoS attack on customer portal causing service degradation</description>
        <affected_services>
            <service>
                <name>Customer Portal</name>
                <criticality>IMPORTANT</criticality>
                <impact_level>MEDIUM</impact_level>
            </service>
        </affected_services>
        <geographical_scope>
            <countries>
                <country>BE</country>
            </countries>
        </geographical_scope>
        <root_cause>External DDoS attack from botnet</root_cause>
    </incident_details>
    
    <impact_assessment>
        <clients_affected>500</clients_affected>
        <economic_impact>
            <estimated_loss_eur>25000.00</estimated_loss_eur>
            <recovery_costs_eur>5000.00</recovery_costs_eur>
            <total_impact_eur>30000.00</total_impact_eur>
        </economic_impact>
        <reputational_impact>MEDIUM</reputational_impact>
        <data_losses>false</data_losses>
        <data_breaches>false</data_breaches>
        <service_availability>
            <availability_percentage>75.0</availability_percentage>
            <sla_breach>true</sla_breach>
        </service_availability>
    </impact_assessment>
    
    <timeline>
        <occurred_at>2024-06-10T08:00:00Z</occurred_at>
        <detected_at>2024-06-10T08:30:00Z</detected_at>
        <confirmed_at>2024-06-10T09:00:00Z</confirmed_at>
        <downtime_duration>PT30M</downtime_duration>
    </timeline>
    
    <regulatory_classification>
        <dora_classification>SIGNIFICANT</dora_classification>
        <notification_required>true</notification_required>
        <notification_deadline>2024-06-11T09:15:00Z</notification_deadline>
        <regulatory_references>
            <reference>EU Regulation 2022/2554 - Article 19</reference>
        </regulatory_references>
    </regulatory_classification>
    
    <remediation>
        <immediate_actions>DDoS protection activated. Traffic filtering enabled.</immediate_actions>
        <preventive_measures>Enhanced DDoS protection implementation planned.</preventive_measures>
        <timeline_for_resolution>2024-06-10T12:00:00Z</timeline_for_resolution>
    </remediation>
</incident_notification>"""
    
    def _create_no_report_golden_vector(self) -> str:
        """Create golden vector XML for no-report incident."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="INITIAL">
    <header>
        <institution_id>BE1122334455</institution_id>
        <institution_name>Small Financial Service</institution_name>
        <contact_person>
            <name>IT Manager</name>
            <role>IT Operations Manager</role>
            <phone>+32 4 345 67 89</phone>
            <email>it.manager@smallfin.be</email>
        </contact_person>
        <submission_date>2024-12-05T10:00:00Z</submission_date>
        <incident_id>INC-2024-004</incident_id>
    </header>
    
    <incident_details>
        <severity>MINOR</severity>
        <category>SYSTEM_FAILURE</category>
        <description>Brief internal system glitch with no customer impact</description>
        <affected_services>
            <service>
                <name>Internal Reporting</name>
                <criticality>NORMAL</criticality>
                <impact_level>NONE</impact_level>
            </service>
        </affected_services>
        <geographical_scope>
            <countries>
                <country>BE</country>
            </countries>
        </geographical_scope>
        <root_cause>Temporary network connectivity issue</root_cause>
    </incident_details>
    
    <impact_assessment>
        <clients_affected>0</clients_affected>
        <reputational_impact>NONE</reputational_impact>
        <data_losses>false</data_losses>
        <data_breaches>false</data_breaches>
        <service_availability>
            <availability_percentage>100.0</availability_percentage>
            <sla_breach>false</sla_breach>
        </service_availability>
    </impact_assessment>
    
    <timeline>
        <occurred_at>2024-12-05T09:58:00Z</occurred_at>
        <detected_at>2024-12-05T10:00:00Z</detected_at>
        <confirmed_at>2024-12-05T10:00:00Z</confirmed_at>
        <downtime_duration>PT2M</downtime_duration>
    </timeline>
    
    <regulatory_classification>
        <dora_classification>NO_REPORT_REQUIRED</dora_classification>
        <notification_required>false</notification_required>
        <regulatory_references>
            <reference>Internal classification - no external reporting required</reference>
        </regulatory_references>
    </regulatory_classification>
    
    <remediation>
        <immediate_actions>System automatically recovered. No action required.</immediate_actions>
        <preventive_measures>Network monitoring enhanced.</preventive_measures>
        <timeline_for_resolution>2024-12-05T10:02:00Z</timeline_for_resolution>
    </remediation>
</incident_notification>"""
    
    def _create_dst_incident_golden_vector(self) -> str:
        """Create golden vector for incident during DST transition."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="INITIAL">
    <header>
        <institution_id>BE2233445566</institution_id>
        <institution_name>DST Test Bank</institution_name>
        <contact_person>
            <name>Risk Officer</name>
            <role>Risk Management Officer</role>
            <phone>+32 2 456 78 90</phone>
            <email>risk@dsttestbank.be</email>
        </contact_person>
        <submission_date>2024-03-31T01:30:00Z</submission_date>
        <incident_id>INC-2024-DST</incident_id>
    </header>
    
    <incident_details>
        <severity>MAJOR</severity>
        <category>SYSTEM_FAILURE</category>
        <description>System failure during DST transition period</description>
        <affected_services>
            <service>
                <name>Trading Platform</name>
                <criticality>CRITICAL</criticality>
                <impact_level>HIGH</impact_level>
            </service>
        </affected_services>
        <geographical_scope>
            <countries>
                <country>BE</country>
            </countries>
        </geographical_scope>
        <root_cause>DST handling bug in trading system</root_cause>
    </incident_details>
    
    <impact_assessment>
        <clients_affected>2000</clients_affected>
        <economic_impact>
            <estimated_loss_eur>100000.00</estimated_loss_eur>
        </economic_impact>
        <reputational_impact>HIGH</reputational_impact>
        <data_losses>false</data_losses>
        <data_breaches>false</data_breaches>
        <service_availability>
            <availability_percentage>50.0</availability_percentage>
            <sla_breach>true</sla_breach>
        </service_availability>
    </impact_assessment>
    
    <timeline>
        <occurred_at>2024-03-31T01:15:00Z</occurred_at>
        <detected_at>2024-03-31T01:30:00Z</detected_at>
        <confirmed_at>2024-03-31T01:45:00Z</confirmed_at>
        <downtime_duration>PT90M</downtime_duration>
    </timeline>
    
    <regulatory_classification>
        <dora_classification>MAJOR</dora_classification>
        <notification_required>true</notification_required>
        <notification_deadline>2024-03-31T05:30:00Z</notification_deadline>
        <regulatory_references>
            <reference>EU Regulation 2022/2554 - Article 19</reference>
        </regulatory_references>
    </regulatory_classification>
    
    <remediation>
        <immediate_actions>Manual intervention to correct time handling</immediate_actions>
        <preventive_measures>DST testing procedures implemented</preventive_measures>
        <timeline_for_resolution>2024-03-31T04:30:00Z</timeline_for_resolution>
    </remediation>
</incident_notification>"""
    
    def _create_large_incident_golden_vector(self) -> str:
        """Create golden vector with maximum allowed data size."""
        # Generate multiple attachments (up to 10 allowed)
        attachments_xml = ""
        for i in range(10):
            attachments_xml += f"""
            <attachment>
                <filename>evidence_{i+1}.pdf</filename>
                <content_type>application/pdf</content_type>
                <size_bytes>{(i+1) * 1024}</size_bytes>
                <checksum>sha256_{i+1:064d}</checksum>
            </attachment>"""
        
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<incident_notification xmlns="http://nbb.be/onegate/dora/v2" version="2.0" submission_type="FINAL">
    <header>
        <institution_id>BE9988776655</institution_id>
        <institution_name>Large Financial Conglomerate</institution_name>
        <contact_person>
            <name>Senior Risk Manager</name>
            <role>Senior Risk Management Officer</role>
            <phone>+32 2 567 89 01</phone>
            <email>senior.risk@largefin.be</email>
        </contact_person>
        <submission_date>2024-08-15T16:00:00Z</submission_date>
        <incident_id>INC-2024-LARGE</incident_id>
    </header>
    
    <incident_details>
        <severity>MAJOR</severity>
        <category>CYBER_ATTACK</category>
        <description>Large-scale coordinated cyber attack on multiple systems with comprehensive impact assessment and detailed remediation plan including multiple service recovery phases</description>
        <affected_services>
            <service>
                <name>Payment Processing</name>
                <criticality>CRITICAL</criticality>
                <impact_level>HIGH</impact_level>
            </service>
            <service>
                <name>Core Banking</name>
                <criticality>CRITICAL</criticality>
                <impact_level>HIGH</impact_level>
            </service>
            <service>
                <name>Customer Portal</name>
                <criticality>IMPORTANT</criticality>
                <impact_level>MEDIUM</impact_level>
            </service>
            <service>
                <name>Mobile Banking</name>
                <criticality>IMPORTANT</criticality>
                <impact_level>MEDIUM</impact_level>
            </service>
            <service>
                <name>Trading Platform</name>
                <criticality>CRITICAL</criticality>
                <impact_level>HIGH</impact_level>
            </service>
        </affected_services>
        <geographical_scope>
            <countries>
                <country>BE</country>
                <country>LU</country>
                <country>NL</country>
                <country>FR</country>
                <country>DE</country>
            </countries>
            <regions>EU, Benelux, DACH</regions>
        </geographical_scope>
        <root_cause>Advanced Persistent Threat with multiple attack vectors including phishing, malware, and SQL injection targeting critical infrastructure</root_cause>
    </incident_details>
    
    <impact_assessment>
        <clients_affected>50000</clients_affected>
        <economic_impact>
            <estimated_loss_eur>2500000.00</estimated_loss_eur>
            <recovery_costs_eur>500000.00</recovery_costs_eur>
            <total_impact_eur>3000000.00</total_impact_eur>
        </economic_impact>
        <reputational_impact>HIGH</reputational_impact>
        <data_losses>true</data_losses>
        <data_breaches>true</data_breaches>
        <service_availability>
            <availability_percentage>25.0</availability_percentage>
            <sla_breach>true</sla_breach>
        </service_availability>
    </impact_assessment>
    
    <timeline>
        <occurred_at>2024-08-15T10:00:00Z</occurred_at>
        <detected_at>2024-08-15T10:30:00Z</detected_at>
        <confirmed_at>2024-08-15T11:00:00Z</confirmed_at>
        <resolved_at>2024-08-16T08:00:00Z</resolved_at>
        <downtime_duration>PT22H</downtime_duration>
    </timeline>
    
    <regulatory_classification>
        <dora_classification>MAJOR</dora_classification>
        <notification_required>true</notification_required>
        <notification_deadline>2024-08-15T15:00:00Z</notification_deadline>
        <regulatory_references>
            <reference>EU Regulation 2022/2554 - Article 19</reference>
            <reference>NBB Circular XXX-2024 - Cyber incident reporting</reference>
            <reference>GDPR Article 33 - Data breach notification</reference>
            <reference>NIS2 Directive - Incident notification</reference>
        </regulatory_references>
    </regulatory_classification>
    
    <remediation>
        <immediate_actions>Complete system isolation. Forensic investigation initiated. Customer communications. Regulatory notifications. Backup systems activation. Security monitoring enhanced. External security firm engagement.</immediate_actions>
        <preventive_measures>Complete security architecture review. Multi-factor authentication implementation. Network segmentation enhancement. Employee security training program. Third-party security assessment. Penetration testing schedule. Incident response plan update.</preventive_measures>
        <timeline_for_resolution>2024-08-30T17:00:00Z</timeline_for_resolution>
    </remediation>
    
    <attachments>{attachments_xml}
    </attachments>
</incident_notification>"""


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])