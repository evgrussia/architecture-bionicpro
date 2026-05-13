import React, { useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

type ReportItem = {
  day: string;
  country: string;
  prosthetic_model: string;
  steps_total: number;
  motor_load_avg: number;
  battery_min: number;
  errors_count: number;
};

type Report = {
  user_id: string;
  period: { from: string; to: string };
  requested_to?: string;
  watermark: string | null;
  items: ReportItem[];
  summary: { days: number; steps_total: number; errors_count: number };
  warning?: string;
};

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);

  const downloadReport = async () => {
    if (!keycloak?.token) {
      setError('Not authenticated');
      return;
    }

    try {
      setLoading(true);
      setError(null);
      setReport(null);

      await keycloak.updateToken(30);

      const response = await fetch(`${process.env.REACT_APP_API_URL}/reports`, {
        headers: {
          Authorization: `Bearer ${keycloak.token}`,
        },
      });

      if (response.status === 401) {
        keycloak.login();
        return;
      }
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }
      const data: Report = await response.json();
      setReport(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  if (!initialized) {
    return <div>Loading...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-start min-h-screen bg-gray-100 py-10">
      <div className="p-8 bg-white rounded-lg shadow-md w-full max-w-4xl">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">Usage Reports</h1>
          <button
            onClick={() => keycloak.logout()}
            className="px-3 py-1 text-sm bg-gray-200 rounded hover:bg-gray-300"
          >
            Logout
          </button>
        </div>

        <button
          onClick={downloadReport}
          disabled={loading}
          className={`px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 ${
            loading ? 'opacity-50 cursor-not-allowed' : ''
          }`}
        >
          {loading ? 'Generating Report...' : 'Get Report'}
        </button>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}

        {report && (
          <div className="mt-6">
            <div className="text-sm text-gray-600 mb-3">
              Период:&nbsp;<b>{report.period.from}</b> — <b>{report.period.to}</b>
              {report.watermark && (
                <span className="ml-3">ETL watermark: {report.watermark}</span>
              )}
            </div>

            {report.warning && (
              <div className="mb-3 p-3 bg-yellow-100 text-yellow-800 rounded">
                {report.warning}
              </div>
            )}

            <div className="grid grid-cols-3 gap-3 mb-4">
              <Card title="Дней в отчёте" value={report.summary.days} />
              <Card title="Шагов всего" value={report.summary.steps_total} />
              <Card title="Ошибок устройства" value={report.summary.errors_count} />
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-100">
                  <tr>
                    <th className="px-3 py-2 text-left">День</th>
                    <th className="px-3 py-2 text-left">Модель</th>
                    <th className="px-3 py-2 text-right">Шаги</th>
                    <th className="px-3 py-2 text-right">Нагрузка</th>
                    <th className="px-3 py-2 text-right">Батарея min</th>
                    <th className="px-3 py-2 text-right">Ошибки</th>
                  </tr>
                </thead>
                <tbody>
                  {report.items.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-3 py-4 text-center text-gray-500">
                        Нет данных за выбранный период.
                      </td>
                    </tr>
                  )}
                  {report.items.map((it) => (
                    <tr key={it.day} className="border-t">
                      <td className="px-3 py-2">{it.day}</td>
                      <td className="px-3 py-2">{it.prosthetic_model}</td>
                      <td className="px-3 py-2 text-right">{it.steps_total}</td>
                      <td className="px-3 py-2 text-right">{it.motor_load_avg.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right">{it.battery_min.toFixed(0)}%</td>
                      <td className="px-3 py-2 text-right">{it.errors_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const Card: React.FC<{ title: string; value: number }> = ({ title, value }) => (
  <div className="p-3 bg-gray-50 rounded border">
    <div className="text-xs text-gray-500">{title}</div>
    <div className="text-xl font-semibold">{value}</div>
  </div>
);

export default ReportPage;
