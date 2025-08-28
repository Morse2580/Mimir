# Belgian RegOps - Lawyer Review Interface

A minimal yet production-ready Next.js 14 application for legal review of regulatory obligation mappings under DORA and NIS2 compliance requirements.

## Features

- **Review Queue**: SLA-aware review queue with priority indicators (Urgent <4h, High <24h)
- **Review Detail**: Evidence preview with one-click approve/reject functionality
- **Decision Management**: Comments required for rejection/revision decisions
- **Concurrent Protection**: Optimistic locking prevents conflicting reviews
- **Belgian/EU Styling**: Professional, clean interface ready for multi-language support
- **Real-time Updates**: 30-second refresh intervals for queue and details

## Quick Start

### Prerequisites
- Node.js 18+
- Python 3.8+ (for backend testing)

### Frontend Setup

1. Install dependencies:
```bash
cd frontend
npm install --legacy-peer-deps
```

2. Run type check:
```bash
npm run type-check
```

3. Start development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:3000`

### Backend Setup (Testing)

1. Install FastAPI dependencies:
```bash
cd backend
python3 -m pip install fastapi uvicorn
```

2. Start the test backend:
```bash
python3 main.py
```

The API will be available at `http://localhost:8000`

## API Integration

The frontend expects the following FastAPI endpoints:

- `GET /api/reviews` - Get reviews with filters
- `GET /api/reviews/{id}` - Get single review  
- `POST /api/reviews/{id}/claim` - Claim review
- `POST /api/reviews/{id}/release` - Release review
- `POST /api/reviews/{id}/decision` - Submit decision
- `GET /api/reviews/stats` - Get dashboard stats

## Key Components

### Review Queue (`/reviews`)
- Filterable by status and priority
- Real-time SLA indicators
- Dashboard statistics
- Auto-refresh every 30 seconds

### Review Detail (`/reviews/[id]`)  
- Evidence file preview
- Mapping details display
- Claim/release functionality
- Decision form with comments

### Decision Form
- Approve/Reject/Needs Revision options
- Required comments for non-approval decisions
- Evidence tracking checkboxes
- Version hash validation for concurrent protection

## Belgian/EU Compliance Features

- **SLA Tracking**: Urgent (4h), High (24h), Normal (72h), Low (1 week)
- **Audit Trail**: Immutable decision records with version control
- **Multi-language Ready**: i18n structure prepared for NL/FR/EN
- **Professional Styling**: Clean, accessible design for legal professionals

## Technology Stack

- **Frontend**: Next.js 14, React 18, TypeScript 5, Tailwind CSS 3
- **State**: TanStack Query, Zustand  
- **Forms**: React Hook Form + Zod validation
- **Icons**: Lucide React
- **Backend**: FastAPI (testing), Python 3.11+

## Production Deployment

The application follows the tech stack specified in CLAUDE.md:

- **Runtime**: Azure Container Apps
- **Auth**: Azure AD (Entra ID) with NextAuth
- **Database**: PostgreSQL 15+ with audit trails  
- **Storage**: Azure Blob Storage for evidence files
- **Monitoring**: Azure Application Insights

## Development Notes

- All times displayed in Brussels timezone (Europe/Brussels)
- Version hashes used for optimistic locking
- 30-second auto-refresh for live updates
- Responsive design for desktop and tablet use
- Accessibility features included (ARIA labels, keyboard navigation)

Built following the Belgian RegOps Platform architectural standards with DORA and NIS2 compliance in mind.