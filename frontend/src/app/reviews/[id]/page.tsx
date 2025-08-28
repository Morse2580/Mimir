import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { ReviewDetail } from '@/components/ReviewDetail';

interface ReviewPageProps {
  params: {
    id: string;
  };
}

export default function ReviewPage({ params }: ReviewPageProps) {
  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between py-6">
            <div className="flex items-center">
              <Link 
                href="/reviews"
                className="mr-4 p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </Link>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">
                  Review Details
                </h1>
                <p className="text-sm text-gray-600">
                  Legal review of regulatory obligation mapping
                </p>
              </div>
            </div>
            <div className="text-sm text-gray-500">
              DORA & NIS2 Compliance
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <ReviewDetail reviewId={params.id} />
      </div>
    </div>
  );
}