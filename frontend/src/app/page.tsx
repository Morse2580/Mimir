import Link from 'next/link';
import { Clock, FileText, AlertTriangle, Users } from 'lucide-react';

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div className="flex items-center">
              <div className="w-8 h-8 bg-primary-600 rounded-lg mr-3"></div>
              <h1 className="text-2xl font-bold text-gray-900">
                Belgian RegOps
              </h1>
            </div>
            <div className="text-sm text-gray-500">
              Lawyer Review Interface
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Welcome to the Legal Review Dashboard
          </h2>
          <p className="text-lg text-gray-600 max-w-2xl mx-auto">
            Professional interface for reviewing regulatory obligation mappings under DORA and NIS2 compliance requirements.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="card p-6">
            <div className="flex items-center">
              <AlertTriangle className="h-8 w-8 text-danger-500 mr-3" />
              <div>
                <p className="text-2xl font-bold text-gray-900">--</p>
                <p className="text-sm text-gray-600">Urgent Reviews</p>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center">
              <Clock className="h-8 w-8 text-warning-500 mr-3" />
              <div>
                <p className="text-2xl font-bold text-gray-900">--</p>
                <p className="text-sm text-gray-600">SLA Breached</p>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center">
              <FileText className="h-8 w-8 text-primary-500 mr-3" />
              <div>
                <p className="text-2xl font-bold text-gray-900">--</p>
                <p className="text-sm text-gray-600">Total Pending</p>
              </div>
            </div>
          </div>

          <div className="card p-6">
            <div className="flex items-center">
              <Users className="h-8 w-8 text-success-500 mr-3" />
              <div>
                <p className="text-2xl font-bold text-gray-900">--</p>
                <p className="text-sm text-gray-600">My Assigned</p>
              </div>
            </div>
          </div>
        </div>

        <div className="text-center">
          <Link 
            href="/reviews"
            className="btn-primary inline-flex items-center text-lg px-8 py-3"
          >
            <FileText className="w-5 h-5 mr-2" />
            View Review Queue
          </Link>
        </div>
      </div>
    </div>
  );
}