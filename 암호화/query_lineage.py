"""
쿼리 리니지 프로그램 - Query Lineage Program
소스 테이블과 타겟 테이블의 관계를 추적하는 프로그램
"""

from dataclasses import dataclass
from typing import List, Dict, Set
from collections import defaultdict, deque


@dataclass
class Query:
    """쿼리 정보를 저장하는 클래스"""
    query_id: str
    query_name: str
    source_tables: List[str]
    target_table: str
    query_sql: str


class QueryLineage:
    """쿼리 리니지를 관리하는 클래스"""
    
    def __init__(self):
        self.queries: Dict[str, Query] = {}
        self.source_to_target: Dict[str, Set[str]] = defaultdict(set)  # 소스 -> 타겟
        self.target_to_source: Dict[str, Set[str]] = defaultdict(set)  # 타겟 -> 소스
    
    def add_query(self, query: Query):
        """쿼리 추가"""
        self.queries[query.query_id] = query
        
        # 관계 설정
        for source_table in query.source_tables:
            self.source_to_target[source_table].add(query.target_table)
            self.target_to_source[query.target_table].add(source_table)
    
    def get_lineage_upstream(self, table_name: str) -> Set[str]:
        """
        상위 리니지 추적 (입력 테이블)
        해당 테이블을 생성하는 소스 테이블들을 추적
        """
        visited = set()
        stack = [table_name]
        
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            
            # 현재 테이블의 소스 테이블 찾기
            sources = self.target_to_source.get(current, set())
            stack.extend(sources)
        
        visited.remove(table_name)  # 자신은 제외
        return visited
    
    def get_lineage_downstream(self, table_name: str) -> Set[str]:
        """
        하위 리니지 추적 (출력 테이블)
        현재 테이블을 사용하는 타겟 테이블들을 추적
        """
        visited = set()
        stack = [table_name]
        
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            
            # 현재 테이블의 타겟 테이블 찾기
            targets = self.source_to_target.get(current, set())
            stack.extend(targets)
        
        visited.remove(table_name)  # 자신은 제외
        return visited
    
    def print_lineage_tree(self, table_name: str, direction: str = "both", level: int = 0):
        """리니지를 트리 형식으로 출력"""
        indent = "  " * level
        
        if level == 0:
            print(f"\n{'='*50}")
            print(f"테이블: {table_name}")
            print(f"방향: {direction}")
            print(f"{'='*50}")
        
        if direction in ["upstream", "both"]:
            if level == 0:
                print(f"\n[↑ 상위 리니지 (입력 소스)]")
            sources = self.target_to_source.get(table_name, set())
            for source in sorted(sources):
                print(f"{indent}├─ {source}")
                if level < 2:  # 깊이 제한
                    self.print_lineage_tree(source, direction="upstream", level=level+1)
        
        if direction in ["downstream", "both"]:
            if level == 0:
                print(f"\n[↓ 하위 리니지 (출력 타겟)]")
            targets = self.source_to_target.get(table_name, set())
            for target in sorted(targets):
                print(f"{indent}├─ {target}")
                if level < 2:  # 깊이 제한
                    self.print_lineage_tree(target, direction="downstream", level=level+1)
    
    def print_query_info(self, query_id: str):
        """쿼리 정보 출력"""
        if query_id not in self.queries:
            print(f"쿼리를 찾을 수 없습니다: {query_id}")
            return
        
        query = self.queries[query_id]
        print(f"\n{'='*50}")
        print(f"쿼리 ID: {query.query_id}")
        print(f"쿼리 이름: {query.query_name}")
        print(f"소스 테이블: {', '.join(query.source_tables)}")
        print(f"타겟 테이블: {query.target_table}")
        print(f"{'='*50}")
        print(f"SQL:\n{query.query_sql}")
        print(f"{'='*50}")
    
    def print_all_lineage(self):
        """모든 리니지 관계 출력"""
        print(f"\n{'='*60}")
        print("전체 쿼리 리니지 관계")
        print(f"{'='*60}")
        
        for query_id, query in sorted(self.queries.items()):
            print(f"\n[{query_id}] {query.query_name}")
            print(f"  소스: {', '.join(query.source_tables)} → 타겟: {query.target_table}")


def main():
    """메인 함수 - 샘플 실행"""
    
    # 리니지 객체 생성
    lineage = QueryLineage()
    
    # 샘플 쿼리 생성 및 추가
    queries = [
        Query(
            query_id="Q001",
            query_name="고객 데이터 통합",
            source_tables=["raw_customer", "raw_address"],
            target_table="customer_master",
            query_sql="SELECT c.*, a.address FROM raw_customer c LEFT JOIN raw_address a ON c.customer_id = a.customer_id"
        ),
        Query(
            query_id="Q002",
            query_name="주문 데이터 통합",
            source_tables=["raw_order", "raw_order_item"],
            target_table="order_master",
            query_sql="SELECT o.*, i.item_count FROM raw_order o JOIN raw_order_item i ON o.order_id = i.order_id"
        ),
        Query(
            query_id="Q003",
            query_name="판매 분석 뷰",
            source_tables=["customer_master", "order_master"],
            target_table="sales_analysis",
            query_sql="SELECT c.customer_name, COUNT(o.order_id) as order_count FROM customer_master c LEFT JOIN order_master o ON c.customer_id = o.customer_id GROUP BY c.customer_id"
        ),
        Query(
            query_id="Q004",
            query_name="고객 매출 집계",
            source_tables=["sales_analysis"],
            target_table="customer_revenue",
            query_sql="SELECT customer_name, SUM(order_amount) as total_revenue FROM sales_analysis GROUP BY customer_name"
        ),
        Query(
            query_id="Q005",
            query_name="일일 매출 리포트",
            source_tables=["order_master"],
            target_table="daily_sales_report",
            query_sql="SELECT DATE(order_date) as sales_date, SUM(order_amount) as daily_total FROM order_master GROUP BY DATE(order_date)"
        ),
        Query(
            query_id="Q006",
            query_name="고객 마스터 병합",
            source_tables=["customer_staging", "customer_master"],
            target_table="customer_master",
            query_sql="""MERGE INTO customer_master t
USING customer_staging s
ON t.customer_id = s.customer_id
WHEN MATCHED THEN 
    UPDATE SET 
        t.customer_name = s.customer_name,
        t.email = s.email,
        t.update_date = SYSDATE
WHEN NOT MATCHED THEN 
    INSERT (customer_id, customer_name, email, create_date, update_date)
    VALUES (s.customer_id, s.customer_name, s.email, SYSDATE, SYSDATE)"""
        ),
        Query(
            query_id="Q007",
            query_name="주문 마스터 병합",
            source_tables=["order_staging", "order_master"],
            target_table="order_master",
            query_sql="""MERGE INTO order_master t
USING order_staging s
ON t.order_id = s.order_id
WHEN MATCHED THEN 
    UPDATE SET 
        t.order_status = s.order_status,
        t.total_amount = s.total_amount,
        t.updated_at = SYSDATE
    DELETE WHERE s.is_deleted = 'Y'
WHEN NOT MATCHED THEN 
    INSERT (order_id, customer_id, order_date, total_amount, order_status, created_at, updated_at)
    VALUES (s.order_id, s.customer_id, s.order_date, s.total_amount, s.order_status, SYSDATE, SYSDATE)"""
        ),
    ]
    
    # 쿼리 추가
    for query in queries:
        lineage.add_query(query)
    
    # ===== 결과 출력 =====
    
    print("\n" + "="*60)
    print("쿼리 리니지 프로그램 - 샘플 실행")
    print("="*60)
    
    # 1. 전체 리니지 출력
    lineage.print_all_lineage()
    
    # 2. 특정 쿼리 정보 출력
    lineage.print_query_info("Q003")
    
    # 3. 특정 테이블의 상위 리니지 (입력 소스)
    print(f"\n{'='*60}")
    print("customer_revenue의 상위 리니지 추적")
    print(f"{'='*60}")
    upstream = lineage.get_lineage_upstream("customer_revenue")
    print(f"영향을 주는 소스 테이블: {', '.join(sorted(upstream))}")
    
    # 4. 특정 테이블의 하위 리니지 (출력 타겟)
    print(f"\n{'='*60}")
    print("customer_master의 하위 리니지 추적")
    print(f"{'='*60}")
    downstream = lineage.get_lineage_downstream("customer_master")
    print(f"영향을 받는 타겟 테이블: {', '.join(sorted(downstream))}")
    
    # 5. 트리 형식 출력
    lineage.print_lineage_tree("sales_analysis", direction="both")
    
    # 6. 최상위 소스 테이블 찾기
    print(f"\n{'='*60}")
    print("최상위 소스 테이블 (Raw Data)")
    print(f"{'='*60}")
    raw_tables = set()
    for table in lineage.source_to_target.keys():
        if table not in lineage.target_to_source:
            raw_tables.add(table)
    print(f"Raw 테이블: {', '.join(sorted(raw_tables))}")
    
    # 7. 최종 타겟 테이블 찾기
    print(f"\n{'='*60}")
    print("최종 타겟 테이블 (최종 결과물)")
    print(f"{'='*60}")
    final_tables = set()
    for table in lineage.target_to_source.keys():
        if table not in lineage.source_to_target:
            final_tables.add(table)
    print(f"최종 테이블: {', '.join(sorted(final_tables))}")


if __name__ == "__main__":
    main()
